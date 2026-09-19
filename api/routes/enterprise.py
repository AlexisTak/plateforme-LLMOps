from __future__ import annotations

import json
import os
import hashlib
import io
import shutil
import zipfile
import re
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field
import requests

from api.enterprise import ROOT, Actor, actor_from_request, metrics, now, require_role, store
from api.jobs import registry
from api.mcp_client import McpError, StreamableHttpClient
from api.paths import PROJECTS_DIR, project_dir
from evaluation.reports import capture_metadata, stale_reasons

router = APIRouter(prefix="/api/enterprise", tags=["enterprise"])


class VersionCreate(BaseModel):
    version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    notes: str = Field(default="", max_length=2000)
    adapter: str | None = Field(default=None, max_length=200)
    quantization: str | None = Field(default=None, max_length=100)
    rag_version: str | None = Field(default=None, max_length=200)
    environment: str = Field(default="local", max_length=50)


class TransitionRequest(BaseModel):
    status: str


class QuotaUpdate(BaseModel):
    max_concurrent_jobs: int = Field(ge=1, le=64)
    max_daily_jobs: int = Field(ge=1, le=10000)
    max_storage_gb: float = Field(ge=1, le=100000)


class AgentBudgetUpdate(BaseModel):
    max_tokens_per_day: int = Field(ge=1, le=100_000_000)
    max_duration_ms_per_day: int = Field(ge=1, le=1000 * 60 * 60 * 24 * 30)  # up to 30 days of cumulative duration
    max_tool_calls_per_day: int = Field(ge=1, le=1_000_000)


class MemberUpdate(BaseModel):
    actor_id: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    name: str = Field(min_length=1, max_length=200)
    role: str


class ProviderUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: str = Field(pattern=r"^(ollama|openai-compatible|anthropic-compatible)$")
    base_url: str = Field(min_length=8, max_length=500)
    model: str = Field(min_length=1, max_length=200)
    api_key_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{1,99}$")
    enabled: bool = True


class ToolUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    method: str = Field(pattern=r"^(GET|POST)$")
    url: str = Field(min_length=8, max_length=500)
    approval_required: bool = False
    timeout_seconds: int = Field(default=5, ge=1, le=30)
    max_response_bytes: int = Field(default=100000, ge=100, le=1000000)
    # LOW/MEDIUM/HIGH/CRITICAL per CLAUDE.md §14 — CRITICAL tools are always gated by
    # approval in evaluate_tool_policy regardless of "allow" policies (defense in depth).
    risk_level: str = Field(default="medium", pattern=r"^(low|medium|high|critical)$")


class ToolExecute(BaseModel):
    arguments: dict = Field(default_factory=dict)


class ApprovalDecision(BaseModel):
    decision: str = Field(pattern=r"^(approved|denied)$")


class ToolPolicyUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    effect: str = Field(pattern=r"^(allow|deny|require_approval)$")
    tool_id: str | None = None
    priority: int = Field(default=100, ge=0, le=1000)
    enabled: bool = True


class McpServerUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=8, max_length=500)
    api_key_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{1,99}$")
    enabled: bool = True


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
    # Reuses the SHA-256 fingerprinting evaluation/reports.py already computes for staleness
    # detection — the model registry entry gets the same provenance for free instead of a
    # second hashing pass over the same files.
    artifacts = {path: info for path, info in capture_metadata(project)["files"].items() if info}
    item = store.create_version(
        project.name, body.version, meta.get("inference_model") or meta["base_model"],
        dataset_version, benchmark_at, current, body.notes,
        adapter=body.adapter, quantization=body.quantization, rag_version=body.rag_version,
        environment=body.environment, artifacts=artifacts,
    )
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


_REQUIREMENT_RE = re.compile(r"^([A-Za-z0-9_.\-\[\]]+)\s*==\s*([A-Za-z0-9_.\-]+)")


def _python_dependencies() -> list[dict[str, str]]:
    path = ROOT / "requirements.txt"
    if not path.exists():
        return []
    deps = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        match = _REQUIREMENT_RE.match(line) if line and not line.startswith("#") else None
        if match:
            deps.append({"name": match.group(1), "version": match.group(2)})
    return deps


@router.get("/projects/{project_id}/registry/{item_id}/sbom")
def registry_sbom(item_id: str, project: Path = Depends(project_dir)):
    """Supply-chain manifest for one model registry entry (CLAUDE.md §16): what exactly
    composed it — base model, dataset version, adapter, RAG version, artifact hashes
    already tracked by the registry, plus the pinned Python dependency versions."""
    item = next((v for v in store.versions(project.name) if v["id"] == item_id), None)
    if not item:
        raise HTTPException(404, "Version de registre inconnue")
    return {
        "schema": "biscuits-sbom-1",
        "generated_at": now(),
        "project_id": project.name,
        "model_version": {k: item[k] for k in (
            "version", "status", "model", "dataset_version", "adapter",
            "quantization", "rag_version", "environment", "created_at", "created_by",
        )},
        "artifacts": item["artifacts"],
        "python_dependencies": _python_dependencies(),
    }


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


@router.get("/projects/{project_id}/budget")
def get_budget(request: Request, project: Path = Depends(project_dir)):
    # Usage figures are activity metadata of the project — members only.
    store.require_project_role(project.name, actor(request))
    return {**store.agent_budget(project.name), **store.agent_budget_usage(project.name)}


@router.put("/projects/{project_id}/budget")
def update_budget(body: AgentBudgetUpdate, request: Request, project: Path = Depends(project_dir)):
    current = actor(request)
    require_role(current, "admin")
    result = store.set_agent_budget(project.name, body.max_tokens_per_day, body.max_duration_ms_per_day, body.max_tool_calls_per_day)
    store.audit(current.id, "budget.updated", "project", project.name, project.name, result)
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


def enforce_agent_budget(project: Path, kind: str) -> None:
    """F14 — checked before starting a new chat exchange (kind="tokens"/"duration",
    api/routes/chat.py) or before actually running a tool (kind="tool_calls",
    execute_tool/decide_approval below). Same before-the-fact style as
    enforce_job_quota: it blocks the *next* call once today's budget is already
    spent, it doesn't cut a running generation off mid-stream."""
    budget = store.agent_budget(project.name)
    usage = store.agent_budget_usage(project.name)
    if kind == "tokens" and usage["tokens_used"] >= budget["max_tokens_per_day"]:
        raise HTTPException(429, f"Budget de jetons atteint : {budget['max_tokens_per_day']} jetons/jour maximum")
    if kind == "duration" and usage["duration_ms_used"] >= budget["max_duration_ms_per_day"]:
        raise HTTPException(429, f"Budget de durée atteint : {budget['max_duration_ms_per_day']} ms/jour maximum")
    if kind == "tool_calls" and usage["tool_calls_used"] >= budget["max_tool_calls_per_day"]:
        raise HTTPException(429, f"Budget d'appels d'outils atteint : {budget['max_tool_calls_per_day']} appels/jour maximum")


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


PROJECT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9\-]{0,62}$")


@router.post("/projects/{project_id}/restore", status_code=201)
async def restore_project(project_id: str, request: Request, file: UploadFile = File(...)):
    """Restore a backup produced by GET .../backup into a brand-new project id.
    Never overwrites an existing project — pick an id that doesn't exist yet.
    Every file's SHA-256 is checked against BACKUP_MANIFEST.json before being
    written; any mismatch or path outside the target directory aborts the
    whole restore and removes the partially-written directory (an uploaded
    archive is untrusted input, CLAUDE.md §23)."""
    current = actor(request)
    require_role(current, "admin")
    if not PROJECT_ID_PATTERN.match(project_id):
        raise HTTPException(400, "id doit etre en minuscules, chiffres et tirets uniquement (1-63 caracteres)")
    target = PROJECTS_DIR / project_id
    if target.exists():
        raise HTTPException(409, f"le projet {project_id} existe déjà — restaure sous un nouvel id")

    raw = await file.read()
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise HTTPException(400, "archive ZIP invalide")

    manifest_names = [n for n in archive.namelist() if n.endswith("BACKUP_MANIFEST.json")]
    if len(manifest_names) != 1:
        raise HTTPException(400, "manifeste de sauvegarde introuvable ou ambigu dans l’archive")
    manifest_name = manifest_names[0]
    root_prefix = manifest_name[: -len("BACKUP_MANIFEST.json")]
    manifest = json.loads(archive.read(manifest_name))
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("files"), dict):
        raise HTTPException(400, "version de manifeste de sauvegarde non supportée")

    target.mkdir(parents=True)
    try:
        for rel_path, expected_sha in manifest["files"].items():
            if rel_path.startswith("/") or ".." in Path(rel_path).parts:
                raise HTTPException(400, f"chemin suspect dans le manifeste : {rel_path}")
            member = root_prefix + rel_path
            if member not in archive.namelist():
                raise HTTPException(409, f"fichier manquant dans l’archive : {rel_path}")
            data = archive.read(member)
            if hashlib.sha256(data).hexdigest() != expected_sha:
                raise HTTPException(409, f"intégrité invalide pour {rel_path} — restauration annulée")
            dest = target / rel_path
            if target.resolve() not in dest.resolve().parents:
                raise HTTPException(400, f"chemin suspect dans le manifeste : {rel_path}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
    except HTTPException:
        shutil.rmtree(target, ignore_errors=True)
        raise

    store.audit(current.id, "project.restored", "project", project_id, project_id, {"files": len(manifest["files"])})
    return {"restored": True, "project_id": project_id, "files": len(manifest["files"])}


@router.get("/projects/{project_id}/executions")
def list_executions(request: Request, project: Path = Depends(project_dir), limit: int = 100):
    store.require_project_role(project.name, actor(request))
    return store.executions(project.name, limit)


@router.get("/projects/{project_id}/executions/{execution_id}")
def get_execution(execution_id: str, request: Request, project: Path = Depends(project_dir)):
    store.require_project_role(project.name, actor(request))
    result = store.execution(project.name, execution_id)
    if not result:
        raise HTTPException(404, "Exécution inconnue")
    return result


@router.get("/projects/{project_id}/executions/{execution_id}/export")
def export_execution(execution_id: str, request: Request, project: Path = Depends(project_dir)):
    store.require_project_role(project.name, actor(request))
    result = store.execution(project.name, execution_id)
    if not result:
        raise HTTPException(404, "Exécution inconnue")
    payload = json.dumps({"schema_version": 1, "execution": result}, ensure_ascii=False, indent=2)
    return Response(payload, media_type="application/json", headers={
        "Content-Disposition": f'attachment; filename="openagent-execution-{execution_id}.json"',
    })


def _provider_url(value: str) -> str:
    value = value.rstrip("/")
    if not re.match(r"^https?://", value):
        raise HTTPException(400, "L’URL doit commencer par http:// ou https://")
    return value


@router.get("/projects/{project_id}/providers")
def list_providers(request: Request, project: Path = Depends(project_dir)):
    store.require_project_role(project.name, actor(request))
    return store.providers(project.name)


@router.put("/projects/{project_id}/providers")
def update_provider(body: ProviderUpdate, request: Request, project: Path = Depends(project_dir)):
    current = actor(request)
    store.require_project_role(project.name, current, "admin")
    result = store.set_provider(project.name, body.name.strip(), body.type, _provider_url(body.base_url),
                                body.model.strip(), body.api_key_env, body.enabled)
    store.audit(current.id, "provider.updated", "provider", result["id"], project.name,
                {"name": result["name"], "type": result["type"], "base_url": result["base_url"]})
    return result


@router.delete("/projects/{project_id}/providers/{provider_id}")
def delete_provider(provider_id: str, request: Request, project: Path = Depends(project_dir)):
    current = actor(request)
    store.require_project_role(project.name, current, "admin")
    if not store.remove_provider(project.name, provider_id):
        raise HTTPException(404, "Fournisseur inconnu")
    store.audit(current.id, "provider.removed", "provider", provider_id, project.name)
    return {"deleted": True}


@router.post("/projects/{project_id}/providers/{provider_id}/test")
def test_provider(provider_id: str, request: Request, project: Path = Depends(project_dir)):
    current = actor(request)
    store.require_project_role(project.name, current, "admin")
    provider = next((item for item in store.providers(project.name) if item["id"] == provider_id), None)
    if not provider:
        raise HTTPException(404, "Fournisseur inconnu")
    headers = {}
    if provider["api_key_env"]:
        secret = os.getenv(provider["api_key_env"], "")
        if not secret:
            raise HTTPException(409, f"Variable {provider['api_key_env']} absente")
        if provider["type"] == "anthropic-compatible":
            headers["x-api-key"] = secret
            headers["anthropic-version"] = "2023-06-01"
        else:
            headers["Authorization"] = f"Bearer {secret}"
    url = provider["base_url"] + ("/api/tags" if provider["type"] == "ollama" else "/v1/models")
    started = time.perf_counter()
    try:
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(502, f"Connexion impossible : {exc}") from exc
    elapsed = round((time.perf_counter() - started) * 1000, 2)
    store.audit(current.id, "provider.tested", "provider", provider_id, project.name, {"ok": True, "latency_ms": elapsed})
    return {"ok": True, "latency_ms": elapsed, "model": provider["model"]}


def _mcp_client(project_id: str, server_id: str) -> StreamableHttpClient:
    server = next((item for item in store.mcp_servers(project_id) if item["id"] == server_id), None)
    if not server or not server["enabled"]:
        raise HTTPException(409, "Serveur MCP inconnu ou désactivé")
    token = None
    if server["api_key_env"]:
        token = os.getenv(server["api_key_env"], "")
        if not token:
            raise HTTPException(409, f"Variable {server['api_key_env']} absente")
    return StreamableHttpClient(server["url"], token)


def _execute_tool(tool: dict, arguments: dict, project_id: str) -> dict:
    started = time.perf_counter()
    try:
        if tool.get("connector_type") == "mcp":
            payload = _mcp_client(project_id, tool["connector_id"]).call_tool(tool["action"], arguments)
            if payload.get("isError") is True:
                raise McpError("Le serveur MCP a signalé un échec de l’outil")
            raw = json.dumps(payload, ensure_ascii=False).encode()
            capped = raw[:tool["max_response_bytes"]]
            return {"status_code": 200, "bytes": len(capped), "truncated": len(raw) > len(capped),
                    "preview": capped.decode("utf-8", errors="replace")[:2000],
                    "duration_ms": round((time.perf_counter()-started)*1000, 2), "protocol": "mcp"}
        if tool["method"] == "GET":
            response = requests.get(tool["url"], params=arguments, timeout=tool["timeout_seconds"])
        else:
            response = requests.post(tool["url"], json=arguments, timeout=tool["timeout_seconds"])
        response.raise_for_status()
    except (requests.RequestException, McpError) as exc:
        raise HTTPException(502, f"Échec de l’outil : {exc}") from exc
    raw = response.content[:tool["max_response_bytes"]]
    return {"status_code": response.status_code, "bytes": len(raw), "truncated": len(response.content) > len(raw),
            "preview": raw.decode("utf-8", errors="replace")[:2000], "duration_ms": round((time.perf_counter()-started)*1000, 2)}


@router.get("/projects/{project_id}/tools")
def list_tools(request: Request, project: Path = Depends(project_dir)):
    store.require_project_role(project.name, actor(request))
    return store.tools(project.name)


@router.put("/projects/{project_id}/tools")
def update_tool(body: ToolUpdate, request: Request, project: Path = Depends(project_dir)):
    current = actor(request)
    store.require_project_role(project.name, current, "admin")
    result = store.set_tool(project.name, body.name.strip(), body.method, _provider_url(body.url),
                            body.approval_required, body.timeout_seconds, body.max_response_bytes, body.risk_level)
    store.audit(current.id, "tool.updated", "tool", result["id"], project.name, {"name": result["name"]})
    return result


@router.post("/projects/{project_id}/tools/{tool_id}/execute")
def execute_tool(tool_id: str, body: ToolExecute, request: Request, project: Path = Depends(project_dir)):
    current = actor(request)
    store.require_project_role(project.name, current, "operator")
    tool = store.tool(project.name, tool_id)
    if not tool or not tool["enabled"]:
        raise HTTPException(404, "Outil inconnu ou désactivé")
    decision = store.evaluate_tool_policy(project.name, tool_id)
    if decision["effect"] == "deny":
        store.audit(current.id, "tool.policy.denied", "tool", tool_id, project.name, decision)
        raise HTTPException(403, decision["reason"])
    if decision["effect"] == "require_approval":
        approval = store.request_approval(project.name, tool_id, current.id, body.arguments)
        store.audit(current.id, "tool.approval.requested", "approval", approval["id"], project.name,
                    {"tool_id": tool_id, "policy": decision})
        return {"status": "pending_approval", "approval": approval}
    enforce_agent_budget(project, "tool_calls")
    result = _execute_tool(tool, body.arguments, project.name)
    store.audit(current.id, "tool.executed", "tool", tool_id, project.name,
                {"result": result, "policy": decision})
    return {"status": "completed", "result": result}


@router.get("/projects/{project_id}/approvals")
def list_approvals(request: Request, project: Path = Depends(project_dir)):
    store.require_project_role(project.name, actor(request), "reviewer")
    return store.approvals(project.name)


@router.post("/projects/{project_id}/approvals/{approval_id}/decision")
def decide_approval(approval_id: str, body: ApprovalDecision, request: Request, project: Path = Depends(project_dir)):
    current = actor(request)
    store.require_project_role(project.name, current, "reviewer")
    approval = store.approval(project.name, approval_id)
    if not approval:
        raise HTTPException(404, "Approbation inconnue")
    result = None
    if body.decision == "approved":
        tool = store.tool(project.name, approval["tool_id"])
        if not tool or not tool["enabled"]:
            raise HTTPException(409, "L’outil n’existe plus ou est désactivé")
        policy = store.evaluate_tool_policy(project.name, approval["tool_id"])
        if policy["effect"] == "deny":
            store.audit(current.id, "tool.policy.denied", "approval", approval_id, project.name,
                        {"tool_id": approval["tool_id"], **policy})
            raise HTTPException(409, "Approbation bloquée : " + policy["reason"])
        enforce_agent_budget(project, "tool_calls")
        store.claim_approval(project.name, approval_id)
        try:
            result = _execute_tool(tool, approval["arguments"], project.name)
        except HTTPException as exc:
            store.fail_claimed_approval(project.name, approval_id, current.id, str(exc.detail))
            store.audit(current.id, "tool.approval.failed", "approval", approval_id, project.name,
                        {"tool_id": approval["tool_id"], "error": str(exc.detail)})
            raise
        except Exception:
            store.fail_claimed_approval(project.name, approval_id, current.id, "Erreur interne de l’outil")
            store.audit(current.id, "tool.approval.failed", "approval", approval_id, project.name,
                        {"tool_id": approval["tool_id"], "error": "internal_error"})
            raise
    decided = store.decide_approval(project.name, approval_id, body.decision, current.id, result)
    store.audit(current.id, f"tool.approval.{body.decision}", "approval", approval_id, project.name, {"tool_id": approval["tool_id"]})
    return decided


@router.get("/projects/{project_id}/tool-policies")
def list_tool_policies(request: Request, project: Path = Depends(project_dir)):
    store.require_project_role(project.name, actor(request))
    return store.policies(project.name)


@router.put("/projects/{project_id}/tool-policies")
def update_tool_policy(body: ToolPolicyUpdate, request: Request, project: Path = Depends(project_dir)):
    current = actor(request)
    store.require_project_role(project.name, current, "admin")
    result = store.set_policy(project.name, body.name.strip(), body.effect, body.tool_id,
                              body.priority, body.enabled)
    store.audit(current.id, "tool.policy.updated", "tool_policy", result["id"], project.name,
                {"name": result["name"], "effect": result["effect"],
                 "tool_id": result["tool_id"], "priority": result["priority"]})
    return result


@router.delete("/projects/{project_id}/tool-policies/{policy_id}")
def delete_tool_policy(policy_id: str, request: Request, project: Path = Depends(project_dir)):
    current = actor(request)
    store.require_project_role(project.name, current, "admin")
    if not store.remove_policy(project.name, policy_id):
        raise HTTPException(404, "Politique inconnue")
    store.audit(current.id, "tool.policy.removed", "tool_policy", policy_id, project.name)
    return {"deleted": True}


@router.get("/projects/{project_id}/mcp-servers")
def list_mcp_servers(request: Request, project: Path = Depends(project_dir)):
    store.require_project_role(project.name, actor(request))
    return store.mcp_servers(project.name)


@router.put("/projects/{project_id}/mcp-servers")
def update_mcp_server(body: McpServerUpdate, request: Request, project: Path = Depends(project_dir)):
    current = actor(request)
    store.require_project_role(project.name, current, "admin")
    result = store.set_mcp_server(project.name, body.name.strip(), _provider_url(body.url),
                                  body.api_key_env, body.enabled)
    store.audit(current.id, "mcp.server.updated", "mcp_server", result["id"], project.name,
                {"name": result["name"], "url": result["url"]})
    return result


@router.post("/projects/{project_id}/mcp-servers/{server_id}/sync")
def sync_mcp_server(server_id: str, request: Request, project: Path = Depends(project_dir)):
    current = actor(request)
    store.require_project_role(project.name, current, "admin")
    server = next((item for item in store.mcp_servers(project.name) if item["id"] == server_id), None)
    if not server or not server["enabled"]:
        raise HTTPException(404, "Serveur MCP inconnu ou désactivé")
    try:
        remote_tools = _mcp_client(project.name, server_id).list_tools()
    except McpError as exc:
        raise HTTPException(502, str(exc)) from exc
    imported = store.sync_mcp_tools(project.name, server_id, remote_tools)
    skipped = len(remote_tools) - len(imported)
    store.audit(current.id, "mcp.catalog.synced", "mcp_server", server_id, project.name,
                {"discovered": len(remote_tools), "imported_read_only": len(imported), "skipped": skipped})
    return {"discovered": len(remote_tools), "imported": len(imported), "skipped": skipped, "tools": imported}
