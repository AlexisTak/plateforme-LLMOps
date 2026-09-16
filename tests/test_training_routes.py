"""config_filename is joined onto a filesystem path and passed to a training
subprocess (api/routes/training.py, api/jobs.py) — must never accept traversal."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.paths import project_dir
from api.routes import training


def _client(project: Path) -> TestClient:
    app = FastAPI()
    app.include_router(training.router)
    app.dependency_overrides[project_dir] = lambda: project
    return TestClient(app)


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "demo"
    (project / "training" / "configs").mkdir(parents=True)
    return project


def test_start_training_rejects_path_traversal_config_filename(tmp_path: Path):
    project = _project(tmp_path)
    client = _client(project)
    for bad in ("../secret.yaml", "../../etc/passwd.yaml", "/etc/passwd.yaml", "a/b.yaml", "no-extension"):
        response = client.post("/api/projects/demo/training/start", json={"config_filename": bad})
        assert response.status_code == 422, bad


def test_start_pipeline_rejects_path_traversal_config_filename(tmp_path: Path):
    project = _project(tmp_path)
    client = _client(project)
    response = client.post("/api/projects/demo/training/pipeline", json={
        "config_filename": "../../secret.yaml", "dataset_version": "v1",
    })
    assert response.status_code == 422


def test_start_training_accepts_well_formed_filename_and_404s_when_missing(tmp_path: Path):
    """Proves the traversal fix doesn't reject legitimate names — a well-formed but
    nonexistent config still reaches the file lookup and gets a clean 404, not a 422."""
    project = _project(tmp_path)
    client = _client(project)
    response = client.post("/api/projects/demo/training/start", json={"config_filename": "lora_r16.yaml"})
    assert response.status_code == 404
