"""Liveness vs readiness — /api/health never checks dependencies, /api/ready
does (SQLite store, projects/ directory). Backs the docker-compose healthchecks."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_is_always_ok():
    from api.main import app
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_reports_503_when_projects_dir_missing(tmp_path, monkeypatch):
    from api import main
    monkeypatch.setattr(main, "PROJECTS_DIR", tmp_path / "does-not-exist")
    response = TestClient(main.app).get("/api/ready")
    assert response.status_code == 503


def test_ready_ok_when_dependencies_reachable():
    from api.main import app
    response = TestClient(app).get("/api/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
