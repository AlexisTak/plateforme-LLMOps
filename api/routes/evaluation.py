"""Trigger evaluation/run.py as a background job (see api/routes/jobs.py for status)."""

from __future__ import annotations

from fastapi import APIRouter

from api.jobs import registry
from api.schemas import JobStatus

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])


@router.post("/run", response_model=JobStatus)
def run_evaluation():
    job = registry.start_evaluation()
    return JobStatus(
        job_id=job.job_id,
        kind="evaluation",
        status=job.status,
        config_filename=None,
        started_at=job.started_at,
        log_tail=[],
    )
