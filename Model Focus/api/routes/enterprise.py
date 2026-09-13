from __future__ import annotations

import json
import os
import hashlib
import io
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from api.enterprise import Actor, actor_from_request, metrics, require_role, store
from api.jobs import registry
from api.paths import project_dir
from evaluation.reports import stale_reasons

router = APIRouter(prefix="/api/enterprise", tags=["enterprise"])


class VersionCreate(BaseModel):
    version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    notes: str = Field(default="", max_length=2000)


class TransitionRequest(BaseModel):
    status: str


class QuotaUpdate(BaseModel):
    max_concurrent_jobs: int = Field(ge=1, le=64)
    max_daily_jobs: int = Field(ge=1, le=10000)
    max_storage_gb: float = Field(ge=1, le=100000)


class MemberUpdate(BaseModel):
    actor_id: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    name: str = Field(min_length=1, max_length=200)
    role: str


def actor(request: Request) -> Actor:
    return actor_from_request(request)


@router.get("/context")
def context(request: Request):
    current = actor(request)
    return {"actor": current.__dict__, "auth_mode": os.getenv("BISCUITS_AUTH_MODE", "local"),
            "audit_chain_valid": store.verify_audit_chain()}


@router.get("/metrics")
def get_metrics():
    jobs = registry.list()
    return {**metrics.snapshot(), "jobs_running": sum(j.status == "running" for j in jobs),
            "jobs_failed": sum(j.status == "failed" for j in jobs), "jobs_total": len(jobs)}


@router.get("/metrics/prometheus")
def prometheus_metrics():
    jobs = registry.list()
    values = {**metrics.snapshot(), "jobs_running": sum(j.status == "running" for j in jobs),
              "jobs_failed": sum(j.status == "failed" for j in jobs), "jobs_total": len(jobs)}
    lines = ["# TYPE biscuits_uptime_seconds gauge", f"biscuits_uptime_seconds {values['uptime_seconds']}"]
    for key in ("requests_total", "status_2xx", "status_4xx", "status_5xx", "jobs_running", "jobs_failed", "jobs_total"):
        lines.extend((f"# TYPE biscuits_{key} gauge", f"biscuits_{key} {values.get(key, 0)}"))
    for key in ("latency_avg_ms", "latency_p95_ms"):
        lines.extend((f"# TYPE biscuits_{key} gauge", f"biscuits_{key} {values[key]}"))
    return Response("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


@router.get("/audit")
def audit_log(request: Request, project_id: str | None = None, limit: int = 100):
    require_role(actor(request), "reviewer")
    return store.audits(project_id, limit)


@router.get("/projects/{project_id}/registry")
def list_versions(project: Path = Depends(project_dir)):
    return store.versions(project.name)


@router.post("/projects/{project_id}/registry", status_code=201)
def create_version(body: VersionCreate, request: Request, project: Path = Depends(project_dir)):
    current = actor(request)
    require_role(current, "operator")
    meta = json.loads((project / "meta.json").read_text(encoding="utf-8"))
    dataset_file = project / "data" / "VERSION"
    dataset_version = dataset_file.read_text(encoding="utf-8").strip() if dataset_file.exists() else None
    report_meta = project / "evaluation" / "report_summary.json"
    benchmark_at = None
    if report_meta.exists():
        benchmark_at = json.loads(report_meta.read_text(encoding="utf-8")).get("metadata", {}).get("generated_at")
    item = store.create_version(project.name, body.version, meta.get("inference_model") or meta["base_model"],
                                dataset_version, benchmark_at, current, body.notes)
    store.audit(current.id, "model.version.created", "model_version", item["id"], project.name, {"version": body.version})
    return item


@router.post("/projects/{project_id}/registry/{item_id}/transition")
def transition(item_id: str, body: TransitionRequest, request: Request, project: Path = Depends(project_dir)):
    current = actor(request)
    require_role(current, "reviewer" if body.status in {"approved", "production"} else "operator")
    if body.status not in {"draft", "evaluated", "approved", "production", "archived"}:
        raise HTTPException(400, "Statut inconnu")
    if body.status in {"evaluated", "approved", "production"}:
        report_path = project / "evaluation" / "report_summary.json"
        if not report_path.exists():
            raise HTTPException(409, "Lance un benchmark avant cette transition")
        reasons = stale_reasons(project, json.loads(report_path.read_text(encoding="utf-8")).get("metadata", {}))
        if reasons:
            raise HTTPException(409, "Le benchmark n’est plus à jour : " + " ".join(reasons))
    item = store.transition(project.name, item_id, body.status, current)
    store.audit(current.id, "model.status.changed", "model_version", item_id, project.name, {"status": body.status})
    return item


@router.get("/projects/{project_id}/quota")
def get_quota(project: Path = Depends(project_dir)):
    quota = store.quota(project.name)
    running = sum(j.status == "running" for j in registry.list(project))
    used = sum(path.stat().st_size for path in project.rglob("*") if path.is_file()) / 1024 ** 3
    return {**quota, "running_jobs": running, "storage_used_gb": round(used, 3)}


@router.put("/projects/{project_id}/quota")
def update_quota(body: QuotaUpdate, request: Request, project: Path = Depends(project_dir)):
    current = actor(request)
    require_role(current, "admin")
    result = store.set_quota(project.name, body.max_concurrent_jobs, body.max_daily_jobs, body.max_storage_gb)
    store.audit(current.id, "quota.updated", "project", project.name, project.name, result)
    return result


@router.get("/projects/{project_id}/members")
def list_members(request: Request, project: Path = Depends(project_dir)):
    current = actor(request)
    store.require_project_role(project.name, current)
    return store.members(project.name)


@router.put("/projects/{project_id}/members")
def update_member(body: MemberUpdate, request: Request, project: Path = Depends(project_dir)):
    current = actor(request)
    store.require_project_role(project.name, current, "admin")
    result = store.set_member(project.name, body.actor_id, body.email, body.name, body.role)
    store.audit(current.id, "member.updated", "project_member", body.actor_id, project.name, {"role": body.role})
    return result


@router.delete("/projects/{project_id}/members/{actor_id}")
def delete_member(actor_id: str, request: Request, project: Path = Depends(project_dir)):
    current = actor(request)
    store.require_project_role(project.name, current, "admin")
    if actor_id == current.id:
        raise HTTPException(409, "Tu ne peux pas retirer ton propre accès")
    if not store.remove_member(project.name, actor_id):
        raise HTTPException(404, "Membre inconnu")
    store.audit(current.id, "member.removed", "project_member", actor_id, project.name)
    return {"deleted": True}


def enforce_job_quota(project: Path) -> None:
    quota = store.quota(project.name)
    jobs = registry.list(project)
    running = sum(j.status == "running" for j in jobs)
    if running >= quota["max_concurrent_jobs"]:
        raise HTTPException(429, f"Quota atteint : {quota['max_concurrent_jobs']} jobs simultanés maximum")
    today = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).date().isoformat()
    if sum(j.started_at.startswith(today) for j in jobs) >= quota["max_daily_jobs"]:
        raise HTTPException(429, f"Quota quotidien atteint : {quota['max_daily_jobs']} jobs maximum")
    used_gb = sum(path.stat().st_size for path in project.rglob("*") if path.is_file()) / 1024 ** 3
    if used_gb >= quota["max_storage_gb"]:
        raise HTTPException(429, f"Quota stockage atteint : {quota['max_storage_gb']} Go maximum")


@router.get("/projects/{project_id}/deployment")
def deployment_manifest(project: Path = Depends(project_dir)):
    production = next((item for item in store.versions(project.name) if item["status"] == "production"), None)
    if not production:
        raise HTTPException(404, "Aucune version en production")
    return {
        "schema_version": 1, "project": project.name, "release": production["version"],
        "model": production["model"], "dataset_version": production["dataset_version"],
        "benchmark_generated_at": production["benchmark_generated_at"],
        "runtime": {"healthcheck": "/api/health", "management_port": 8000},
        "configuration": {"BISCUITS_AUTH_MODE": os.getenv("BISCUITS_AUTH_MODE", "local"),
                          "BISCUITS_ENTERPRISE_DB": str(store.path)},
    }


@router.get("/projects/{project_id}/backup")
def backup_project(request: Request, project: Path = Depends(project_dir)):
    current = actor(request)
    store.require_project_role(project.name, current, "operator")
    excluded = {"models/base", "models/merged", "models/quantized", "rag/index", "rag/embeddings"}
    files = [path for path in project.rglob("*") if path.is_file() and not any(str(path.relative_to(project)).startswith(prefix) for prefix in excluded)]
    manifest = {str(path.relative_to(project)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, f"{project.name}/{path.relative_to(project)}")
        archive.writestr(f"{project.name}/BACKUP_MANIFEST.json", json.dumps({"schema_version": 1, "files": manifest}, indent=2))
    store.audit(current.id, "project.backup.created", "project", project.name, project.name, {"files": len(files)})
    return Response(buffer.getvalue(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{project.name}-backup.zip"'})
