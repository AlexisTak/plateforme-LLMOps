"""Generic job status/list/stop endpoints, shared by training and evaluation runs.

Jobs are global (a job_id is unique across all projects — a job belongs to
whichever project it was launched against, tracked on the Job dataclass), so
/api/jobs/{id} works without a project prefix. Listing can optionally be
scoped to one project via /api/projects/{project_id}/jobs.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, HTTPException

from api.jobs import registry
from api.paths import project_dir
from api.schemas import JobStatus, TrainingMetricPoint

router = APIRouter(tags=["jobs"])


def _friendly_error(job) -> tuple[str | None, str | None, str | None]:
    if job.status != "failed":
        return None, None, None
    text = "\n".join(job.stdout_lines[-200:]).lower()
    rules = [
        (("repo id must use", "repository not found", "is not a valid model identifier"), "model_invalid",
         "Le modèle configuré est introuvable ou son identifiant est invalide.",
         "Choisis un identifiant Hugging Face au format organisation/modèle et lance la prévalidation."),
        (("cuda out of memory", "outofmemoryerror"), "cuda_oom",
         "La mémoire du GPU est insuffisante pour ce job.",
         "Réduis la taille du modèle, la longueur de séquence ou le batch size."),
        (("no module named", "modulenotfounderror"), "missing_dependency",
         "Une dépendance Python nécessaire n'est pas installée.",
         "Réinstalle l'environnement avec ./setup-linux.sh puis redémarre l'API."),
        (("validation failed", "invalid json", "no examples"), "dataset_invalid",
         "Le dataset n'a pas passé la validation.",
         "Ouvre Dataset, corrige les erreurs signalées puis reconstruis les splits."),
        (("already exists", "adapter existant"), "artifact_exists",
         "Un résultat existe déjà pour cette configuration.",
         "Active Reprendre/écraser ou choisis un autre nom de configuration."),
        (("connectionerror", "timed out", "temporary failure"), "network_error",
         "Le téléchargement ou l'accès réseau a échoué.",
         "Vérifie la connexion puis relance ; les fichiers déjà téléchargés restent en cache."),
    ]
    for needles, code, message, suggestion in rules:
        if any(needle in text for needle in needles):
            return code, message, suggestion
    return "job_failed", "Le job s'est arrêté avec une erreur non reconnue.", "Consulte les dernières lignes techniques ci-dessous."


def _to_status(job) -> JobStatus:
    result = None
    if job.kind in ("training", "pipeline") and job.status == "completed" and job.config_filename:
        cfg_path = job.project_dir / "training" / "configs" / job.config_filename
        if cfg_path.exists():
            exp_id = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))["experiment"]["id"]
            result_path = job.project_dir / "experiments" / f"{exp_id}.json"
            if result_path.exists():
                result = json.loads(result_path.read_text(encoding="utf-8"))

    error_code, error_message, suggestion = _friendly_error(job)
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
        error_code=error_code,
        error_message=error_message,
        suggestion=suggestion,
    )


@router.get("/api/jobs", response_model=list[JobStatus])
def list_all_jobs():
    return [_to_status(j) for j in registry.list()]


@router.get("/api/projects/{project_id}/jobs", response_model=list[JobStatus])
def list_project_jobs(project: Path = Depends(project_dir)):
    return [_to_status(j) for j in registry.list(project)]


@router.get("/api/jobs/{job_id}", response_model=JobStatus)
def get_job(job_id: str):
    job = registry.get(job_id)
    if job is None:
        raise HTTPException(404, f"no such job: {job_id}")
    return _to_status(job)


@router.post("/api/jobs/{job_id}/stop")
def stop_job(job_id: str):
    if not registry.stop(job_id):
        raise HTTPException(400, "job not running or not found")
    return {"stopped": True}


@router.get("/api/jobs/{job_id}/metrics", response_model=list[TrainingMetricPoint])
def job_metrics(job_id: str):
    """Live loss curve — reads the JSONL log training/scripts/train.py writes
    per step (training/scripts/train.py's JsonlLoggerCallback), so this works
    while a job is still running, not just after it completes."""
    job = registry.get(job_id)
    if job is None:
        raise HTTPException(404, f"no such job: {job_id}")
    if job.kind not in ("training", "pipeline") or not job.config_filename:
        return []

    cfg_path = job.project_dir / "training" / "configs" / job.config_filename
    if not cfg_path.exists():
        return []
    output_dir = job.project_dir / yaml.safe_load(cfg_path.read_text(encoding="utf-8"))["training"]["output_dir"]
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
