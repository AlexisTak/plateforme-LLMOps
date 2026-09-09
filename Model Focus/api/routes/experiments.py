"""Read-only endpoints over a project's experiments/*.json and evaluation/report.md."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from api.paths import project_dir
from api.schemas import ExperimentResult
from evaluation.reports import stale_reasons

router = APIRouter(prefix="/api/projects/{project_id}", tags=["experiments"])


@router.get("/experiments", response_model=list[ExperimentResult])
def list_experiments(project: Path = Depends(project_dir)):
    experiments_dir = project / "experiments"
    if not experiments_dir.exists():
        return []
    results = []
    for path in sorted(experiments_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        results.append(ExperimentResult(**data))
    return results


@router.get("/evaluation/report")
def get_report(project: Path = Depends(project_dir)):
    report_path = project / "evaluation" / "report.md"
    if not report_path.exists():
        raise HTTPException(404, "no evaluation report yet — run an evaluation first")
    summary_path = project / "evaluation/report_summary.json"
    report = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    metadata = report.get("metadata", {})
    return {"content": report_path.read_text(encoding="utf-8"), "path": str(report_path),
            "metadata": metadata, "stale_reasons": stale_reasons(project, metadata),
            "comparison": report.get("comparison")}


@router.get("/evaluation/report/summary")
def get_report_summary(project: Path = Depends(project_dir)):
    summary_path = project / "evaluation" / "report_summary.json"
    if not summary_path.exists():
        raise HTTPException(404, "no evaluation summary yet — run an evaluation first")
    report = json.loads(summary_path.read_text(encoding="utf-8"))
    # Legacy reports remain readable, but their old JSON scores are not current scores.
    return report.get("summary", report)
