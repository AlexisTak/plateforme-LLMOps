"""Experiment comparison endpoint — reuses the experiments/*.json files
already written by training/scripts/train.py, see api/routes/experiments.py."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _result(experiment_id: str, train_loss: float) -> dict:
    return {
        "experiment_id": experiment_id,
        "config_path": f"training/configs/{experiment_id}.yaml",
        "notes": "",
        "dataset_version": "v1",
        "base_model": "org/base",
        "lora": {"r": 16},
        "train_loss": train_loss,
        "eval_loss": train_loss + 0.1,
        "train_duration_minutes": 5.0,
        "peak_vram_mb": 4096.0,
        "adapter_size_mb": 12.0,
        "output_dir": f"models/adapters/{experiment_id}",
        "git_commit": "abc123",
    }


def _client(project: Path) -> TestClient:
    from api.paths import project_dir
    from api.routes import experiments

    app = FastAPI()
    app.include_router(experiments.router)
    app.dependency_overrides[project_dir] = lambda: project
    return TestClient(app)


def test_compare_returns_only_requested_experiments(tmp_path: Path):
    project = tmp_path / "demo"
    experiments_dir = project / "experiments"
    experiments_dir.mkdir(parents=True)
    (experiments_dir / "exp_a.json").write_text(json.dumps(_result("exp_a", 0.9)), encoding="utf-8")
    (experiments_dir / "exp_b.json").write_text(json.dumps(_result("exp_b", 0.7)), encoding="utf-8")
    (experiments_dir / "exp_c.json").write_text(json.dumps(_result("exp_c", 1.2)), encoding="utf-8")

    client = _client(project)
    response = client.get("/api/projects/demo/experiments/compare", params={"ids": "exp_a,exp_c"})

    assert response.status_code == 200
    ids = [item["experiment_id"] for item in response.json()]
    assert ids == ["exp_a", "exp_c"]
    assert response.json()[0]["git_commit"] == "abc123"


def test_compare_unknown_experiment_is_404(tmp_path: Path):
    project = tmp_path / "demo"
    (project / "experiments").mkdir(parents=True)
    client = _client(project)
    response = client.get("/api/projects/demo/experiments/compare", params={"ids": "does-not-exist"})
    assert response.status_code == 404


def test_compare_empty_ids_is_400(tmp_path: Path):
    project = tmp_path / "demo"
    (project / "experiments").mkdir(parents=True)
    client = _client(project)
    response = client.get("/api/projects/demo/experiments/compare", params={"ids": ""})
    assert response.status_code == 400
