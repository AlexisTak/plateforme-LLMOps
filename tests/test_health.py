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


def test_api_v1_prefix_aliases_the_unversioned_api():
    """CLAUDE.md §18: /api/v1/* is a stable prefix for external SDKs, mirroring
    /api/* without a second implementation (api.main.ApiV1AliasMiddleware)."""
    from api.main import app
    v1 = TestClient(app).get("/api/v1/health")
    unversioned = TestClient(app).get("/api/health")
    assert v1.status_code == unversioned.status_code == 200
    assert v1.json() == unversioned.json() == {"status": "ok"}


def test_api_v1_prefix_leaves_other_paths_untouched():
    from api.main import app
    response = TestClient(app).get("/v1/health")
    assert response.status_code == 404
