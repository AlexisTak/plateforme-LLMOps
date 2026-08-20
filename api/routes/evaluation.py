"""Trigger evaluation/run.py as a background job for one project (see
api/routes/jobs.py for status)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends

from api.jobs import registry
from api.paths import project_dir
from api.schemas import JobStatus

router = APIRouter(prefix="/api/projects/{project_id}/evaluation", tags=["evaluation"])


@router.post("/run", response_model=JobStatus)
def run_evaluation(project: Path = Depends(project_dir)):
    job = registry.start_evaluation(project)
    return JobStatus(
        job_id=job.job_id,
        kind="evaluation",
        status=job.status,
        config_filename=None,
        started_at=job.started_at,
        log_tail=[],
    )
