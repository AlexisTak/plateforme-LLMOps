"""Generic job status/list/stop endpoints, shared by training and evaluation runs."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException

from api.jobs import registry
from api.schemas import JobStatus, TrainingMetricPoint

ROOT = Path(__file__).resolve().parent.parent.parent
EXPERIMENTS_DIR = ROOT / "experiments"
CONFIGS_DIR = ROOT / "training" / "configs"

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _to_status(job) -> JobStatus:
    result = None
    if job.kind in ("training", "pipeline") and job.status == "completed" and job.config_filename:
        cfg_path = ROOT / "training" / "configs" / job.config_filename
        if cfg_path.exists():
            exp_id = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))["experiment"]["id"]
            result_path = EXPERIMENTS_DIR / f"{exp_id}.json"
            if result_path.exists():
                result = json.loads(result_path.read_text(encoding="utf-8"))

    return JobStatus(
        job_id=job.job_id,
        kind=job.kind,
        status=job.status,
        config_filename=job.config_filename,
        started_at=job.started_at,
        finished_at=job.finished_at,
        return_code=job.return_code,
        log_tail=job.stdout_lines[-200:],
        result=result,
    )


@router.get("", response_model=list[JobStatus])
def list_jobs():
    return [_to_status(j) for j in registry.list()]


@router.get("/{job_id}", response_model=JobStatus)
def get_job(job_id: str):
    job = registry.get(job_id)
    if job is None:
        raise HTTPException(404, f"no such job: {job_id}")
    return _to_status(job)


@router.post("/{job_id}/stop")
def stop_job(job_id: str):
    if not registry.stop(job_id):
        raise HTTPException(400, "job not running or not found")
    return {"stopped": True}


@router.get("/{job_id}/metrics", response_model=list[TrainingMetricPoint])
def job_metrics(job_id: str):
    """Live loss curve — reads the JSONL log training/scripts/train.py writes
    per step (training/scripts/train.py's JsonlLoggerCallback), so this works
    while a job is still running, not just after it completes."""
    job = registry.get(job_id)
    if job is None:
        raise HTTPException(404, f"no such job: {job_id}")
    if job.kind not in ("training", "pipeline") or not job.config_filename:
        return []

    cfg_path = CONFIGS_DIR / job.config_filename
    if not cfg_path.exists():
        return []
    output_dir = ROOT / yaml.safe_load(cfg_path.read_text(encoding="utf-8"))["training"]["output_dir"]
    log_path = output_dir / "train_log.jsonl"
    if not log_path.exists():
        return []

    points = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        if "loss" not in entry and "eval_loss" not in entry:
            continue
        points.append(
            TrainingMetricPoint(
                step=entry.get("step", 0),
                epoch=entry.get("epoch"),
                loss=entry.get("loss"),
                eval_loss=entry.get("eval_loss"),
                learning_rate=entry.get("learning_rate"),
            )
        )
    return points
