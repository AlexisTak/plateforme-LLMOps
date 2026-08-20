"""Training config listing + launching training/evaluation runs as background jobs, scoped to one project."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, HTTPException

from api.jobs import registry
from api.paths import project_dir
from api.schemas import CreateConfigRequest, JobStatus, StartPipelineRequest, StartSweepRequest, StartTrainingRequest, TrainingConfigSummary

# Real module names from LlamaForCausalLM (see docs/ENVIRONMENT.md) — attention +
# MLP projections, not guessed. Kept identical across every generated config so
# comparisons isolate the hyperparameters actually being varied.
LORA_TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]

router = APIRouter(prefix="/api/projects/{project_id}/training", tags=["training"])


@router.get("/configs", response_model=list[TrainingConfigSummary])
def list_configs(project: Path = Depends(project_dir)):
    summaries = []
    for path in sorted((project / "training" / "configs").glob("*.yaml")):
        cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
        exp_id = cfg["experiment"]["id"]
        summaries.append(
            TrainingConfigSummary(
                filename=path.name,
                experiment_id=exp_id,
                notes=cfg["experiment"].get("notes"),
                base_model=cfg["model"]["name"],
                lora_r=cfg["lora"]["r"],
                dataset_version=cfg["dataset"]["version"],
                output_dir=cfg["training"]["output_dir"],
                has_result=(project / "experiments" / f"{exp_id}.json").exists(),
            )
        )
    return summaries


@router.post("/configs", response_model=TrainingConfigSummary)
def create_config(body: CreateConfigRequest, project: Path = Depends(project_dir)):
    slug = re.sub(r"[^a-zA-Z0-9_\-]+", "_", body.name.strip()).strip("_").lower()
    if not slug:
        raise HTTPException(400, "name has no usable characters")

    meta = json.loads((project / "meta.json").read_text(encoding="utf-8"))
    base_model = meta["base_model"]

    configs_dir = project / "training" / "configs"
    filename = f"custom_{slug}.yaml"
    config_path = configs_dir / filename
    if config_path.exists():
        raise HTTPException(409, f"{filename} already exists — pick another name")

    experiment_id = f"custom_{slug}"
    if (project / "experiments" / f"{experiment_id}.json").exists() or (project / "models" / "adapters" / experiment_id).exists():
        raise HTTPException(409, f"experiment id '{experiment_id}' already has results/adapter on disk — pick another name")

    alpha = body.lora_alpha if body.lora_alpha is not None else body.lora_r * 2

    config = {
        "experiment": {"id": experiment_id, "notes": body.notes or f"custom config: r={body.lora_r}, lr={body.learning_rate}"},
        "model": {"name": base_model},
        "dataset": {
            "version": body.dataset_version,
            "train_path": "data/train",
            "validation_path": "data/validation",
            "max_seq_length": 1024,
        },
        "quantization": {
            "load_in_4bit": True,
            "bnb_4bit_quant_type": "nf4",
            "bnb_4bit_compute_dtype": "bfloat16",
            "bnb_4bit_use_double_quant": True,
        },
        "lora": {
            "r": body.lora_r,
            "alpha": alpha,
            "dropout": body.lora_dropout,
            "target_modules": LORA_TARGET_MODULES,
            "bias": "none",
            "task_type": "CAUSAL_LM",
        },
        "training": {
            "seed": 42,
            "epochs": body.epochs,
            "learning_rate": body.learning_rate,
            "batch_size": body.batch_size,
            "gradient_accumulation_steps": body.gradient_accumulation_steps,
            "warmup_steps": body.warmup_steps,
            "logging_steps": 10,
            "save_steps": 50,
            "eval_strategy": "steps",
            "eval_steps": 50,
            "output_dir": f"models/adapters/{experiment_id}",
        },
    }

    header = (
        f"# Generated from the web console (Training > Nouvelle config) — r={body.lora_r}, "
        f"alpha={alpha}, lr={body.learning_rate}, epochs={body.epochs}.\n"
        f"# Edit by hand or regenerate with a different name; nothing here is auto-managed after creation.\n\n"
    )
    configs_dir.mkdir(parents=True, exist_ok=True)
    config_path.write_text(header + yaml.safe_dump(config, sort_keys=False, default_flow_style=False), encoding="utf-8")

    return TrainingConfigSummary(
        filename=filename,
        experiment_id=experiment_id,
        notes=config["experiment"]["notes"],
        base_model=base_model,
        lora_r=body.lora_r,
        dataset_version=body.dataset_version,
        output_dir=config["training"]["output_dir"],
        has_result=False,
    )


@router.post("/start", response_model=JobStatus)
def start_training(body: StartTrainingRequest, project: Path = Depends(project_dir)):
    try:
        job = registry.start_training(project, body.config_filename, resume=body.resume)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    return JobStatus(
        job_id=job.job_id,
        kind="training",
        status=job.status,
        config_filename=job.config_filename,
        started_at=job.started_at,
        log_tail=[],
    )


@router.post("/pipeline", response_model=JobStatus)
def start_pipeline(body: StartPipelineRequest, project: Path = Depends(project_dir)):
    """Autonomous run: validate dataset -> rebuild splits -> train, one job.
    Only touches this project's datasets/ / data/ / training/ — never rag/documents/."""
    try:
        job = registry.start_pipeline(project, body.config_filename, body.dataset_version, resume=body.resume)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    return JobStatus(
        job_id=job.job_id,
        kind="pipeline",
        status=job.status,
        config_filename=job.config_filename,
        started_at=job.started_at,
        log_tail=[],
    )


@router.post("/sweep", response_model=JobStatus)
def start_sweep(body: StartSweepRequest, project: Path = Depends(project_dir)):
    """Trains r=8, r=16 and r=32 sequentially, one job — full comparison in one
    click. Requires the project to already have lora_r8/16/32.yaml configs."""
    job = registry.start_sweep(project, body.dataset_version, resume=body.resume)
    return JobStatus(job_id=job.job_id, kind="sweep", status=job.status, started_at=job.started_at, log_tail=[])
