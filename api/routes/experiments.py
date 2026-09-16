"""Read-only endpoints over a project's experiments/*.json and evaluation/report.md."""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from api.paths import project_dir
from api.schemas import ExperimentResult
from evaluation.reports import stale_reasons

router = APIRouter(prefix="/api/projects/{project_id}", tags=["experiments"])

# Same filename-safe charset as scripts/dataset_versions.py's _SAFE_VERSION — experiment
# ids come from training config and are used to build a filesystem path below, so they
# must never contain "/", "..", or other path-traversal characters.
_SAFE_EXPERIMENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


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


@router.get("/experiments/compare", response_model=list[ExperimentResult])
def compare_experiments(ids: str, project: Path = Depends(project_dir)):
    """Fetch specific experiments by id for side-by-side comparison, e.g.
    ?ids=custom_r16,custom_r32. Declared before no route matches a plain
    "compare" id, so this never collides with a real experiment id."""
    wanted = [i.strip() for i in ids.split(",") if i.strip()]
    if not wanted:
        raise HTTPException(400, "ids ne peut pas être vide")
    experiments_dir = (project / "experiments").resolve()
    results = []
    for experiment_id in wanted:
        if not _SAFE_EXPERIMENT_ID.match(experiment_id):
            raise HTTPException(400, f"id d’expérience invalide: {experiment_id}")
        path = (experiments_dir / f"{experiment_id}.json").resolve()
        if experiments_dir not in path.parents or not path.exists():
            raise HTTPException(404, f"experiment inconnu: {experiment_id}")
        results.append(ExperimentResult(**json.loads(path.read_text(encoding="utf-8"))))
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
            "comparison": report.get("comparison"), "outputs": report.get("outputs", {})}


@router.get("/evaluation/report/summary")
def get_report_summary(project: Path = Depends(project_dir)):
    summary_path = project / "evaluation" / "report_summary.json"
    if not summary_path.exists():
        raise HTTPException(404, "no evaluation summary yet — run an evaluation first")
    report = json.loads(summary_path.read_text(encoding="utf-8"))
    # Legacy reports remain readable, but their old JSON scores are not current scores.
    return report.get("summary", report)
