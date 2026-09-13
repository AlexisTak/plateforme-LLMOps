"""Trigger evaluation/run.py as a background job for one project (see
api/routes/jobs.py for status)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from api.jobs import registry
from api.model_preflight import require_ready
from api.paths import project_dir
from api.schemas import BenchmarkCase, JobStatus
from evaluation.run import load_benchmark
from api.routes.enterprise import enforce_job_quota
from api.storage import atomic_write_text

router = APIRouter(prefix="/api/projects/{project_id}/evaluation", tags=["evaluation"])


@router.get("/benchmark", response_model=list[BenchmarkCase])
def get_benchmark(project: Path = Depends(project_dir)):
    return load_benchmark(project / "evaluation" / "benchmark.jsonl")


def _save_benchmark(project: Path, items: list[dict]) -> None:
    import json
    content = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items)
    atomic_write_text(project / "evaluation" / "benchmark.jsonl", content)


@router.post("/benchmark", response_model=BenchmarkCase, status_code=201)
def create_benchmark_case(body: BenchmarkCase, project: Path = Depends(project_dir)):
    items = load_benchmark(project / "evaluation" / "benchmark.jsonl")
    if any(item["id"] == body.id for item in items):
        raise HTTPException(409, f"Le cas {body.id} existe déjà")
    item = body.model_dump()
    _save_benchmark(project, [*items, item])
    return item


@router.put("/benchmark/{case_id}", response_model=BenchmarkCase)
def update_benchmark_case(case_id: str, body: BenchmarkCase, project: Path = Depends(project_dir)):
    items = load_benchmark(project / "evaluation" / "benchmark.jsonl")
    index = next((i for i, item in enumerate(items) if item["id"] == case_id), None)
    if index is None:
        raise HTTPException(404, f"Cas inconnu : {case_id}")
    if body.id != case_id and any(item["id"] == body.id for item in items):
        raise HTTPException(409, f"Le cas {body.id} existe déjà")
    items[index] = body.model_dump()
    _save_benchmark(project, items)
    return items[index]


@router.delete("/benchmark/{case_id}")
def delete_benchmark_case(case_id: str, project: Path = Depends(project_dir)):
    items = load_benchmark(project / "evaluation" / "benchmark.jsonl")
    kept = [item for item in items if item["id"] != case_id]
    if len(kept) == len(items):
        raise HTTPException(404, f"Cas inconnu : {case_id}")
    _save_benchmark(project, kept)
    return {"deleted": True}


@router.post("/run", response_model=JobStatus)
def run_evaluation(project: Path = Depends(project_dir)):
    import json
    enforce_job_quota(project)
    meta = json.loads((project / "meta.json").read_text(encoding="utf-8"))
    try:
        require_ready(meta.get("inference_model") or meta["base_model"])
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(400, f"Prévalidation échouée : {exc}") from exc
    job = registry.start_evaluation(project)
    return JobStatus(
        job_id=job.job_id,
        kind="evaluation",
        status=job.status,
        config_filename=None,
        started_at=job.started_at,
        log_tail=[],
    )
