from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.enterprise import Actor, EnterpriseStore


def test_audit_chain_detects_tampering(tmp_path: Path):
    control = EnterpriseStore(tmp_path / "enterprise.db")
    control.audit("alice", "created", "model", "v1", "demo", {"ok": True})
    control.audit("bob", "approved", "model", "v1", "demo")
    assert control.verify_audit_chain()
    with control._connect() as db:
        db.execute("UPDATE audit_events SET action='tampered' WHERE actor_id='alice'")
    assert not control.verify_audit_chain()


def test_registry_workflow_requires_benchmark(tmp_path: Path):
    control = EnterpriseStore(tmp_path / "enterprise.db")
    actor = Actor("alice", "alice@example.test", "admin", "Alice")
    item = control.create_version("demo", "1.0.0", "org/model", "v1", None, actor, "")
    item = control.transition("demo", item["id"], "evaluated", actor)
    with pytest.raises(Exception) as exc:
        control.transition("demo", item["id"], "approved", actor)
    assert "benchmark" in str(exc.value).lower()


def test_registry_happy_path(tmp_path: Path):
    control = EnterpriseStore(tmp_path / "enterprise.db")
    actor = Actor("alice", "alice@example.test", "admin", "Alice")
    item = control.create_version("demo", "1.0.0", "org/model", "v1", "2026-01-01", actor, "ready")
    for status in ("evaluated", "approved", "production"):
        item = control.transition("demo", item["id"], status, actor)
    assert item["status"] == "production"
    assert item["approved_by"] == "alice"
    item = control.transition("demo", item["id"], "archived", actor)
    item = control.transition("demo", item["id"], "production", actor)
    assert item["status"] == "production"


def test_local_enterprise_endpoints():
    from api.main import app
    client = TestClient(app)
    context = client.get("/api/enterprise/context")
    assert context.status_code == 200
    assert context.json()["actor"]["role"] == "admin"
    metrics = client.get("/api/enterprise/metrics")
    assert metrics.status_code == 200
    assert "latency_p95_ms" in metrics.json()


def test_proxy_viewer_cannot_mutate(monkeypatch):
    from api.main import app
    monkeypatch.setenv("BISCUITS_AUTH_MODE", "proxy")
    monkeypatch.setenv("BISCUITS_PROXY_SECRET", "test-secret")
    client = TestClient(app)
    headers = {
        "x-biscuits-proxy-secret": "test-secret", "x-biscuits-user-id": "viewer-1",
        "x-biscuits-user-email": "viewer@example.test", "x-biscuits-role": "viewer",
    }
    response = client.post("/api/projects", headers=headers, json={})
    assert response.status_code == 403
    assert "operator" in response.json()["detail"]


def test_project_membership_isolated_in_proxy_mode(tmp_path: Path, monkeypatch):
    control = EnterpriseStore(tmp_path / "enterprise.db")
    viewer = Actor("viewer-1", "viewer@example.test", "viewer", "Viewer")
    monkeypatch.setenv("BISCUITS_AUTH_MODE", "proxy")
    assert control.project_role("demo", viewer) is None
    control.set_member("demo", viewer.id, viewer.email, viewer.name, "reviewer")
    assert control.project_role("demo", viewer) == "reviewer"
    assert control.project_role("another-project", viewer) is None


def test_four_eyes_approval_in_proxy_mode(tmp_path: Path, monkeypatch):
    control = EnterpriseStore(tmp_path / "enterprise.db")
    creator = Actor("alice", "alice@example.test", "admin", "Alice")
    reviewer = Actor("bob", "bob@example.test", "admin", "Bob")
    monkeypatch.setenv("BISCUITS_AUTH_MODE", "proxy")
    item = control.create_version("demo", "2.0.0", "org/model", "v2", "2026-01-01", creator, "")
    item = control.transition("demo", item["id"], "evaluated", creator)
    with pytest.raises(Exception, match="ne peut pas aussi"):
        control.transition("demo", item["id"], "approved", creator)
    assert control.transition("demo", item["id"], "approved", reviewer)["approved_by"] == "bob"


def test_prometheus_metrics_endpoint():
    from api.main import app
    response = TestClient(app).get("/api/enterprise/metrics/prometheus")
    assert response.status_code == 200
    assert "biscuits_requests_total" in response.text
