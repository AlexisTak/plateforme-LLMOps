from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.enterprise import Actor, EnterpriseStore
from api.routes.enterprise import ProviderUpdate


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


def test_execution_trace_is_redacted(tmp_path: Path):
    control = EnterpriseStore(tmp_path / "enterprise.db")
    execution_id = control.start_execution("demo", "alice", "org/model", None, True, 42)
    control.finish_execution(execution_id, 120, True, ["guide.md"], 25.4)
    result = control.execution("demo", execution_id)
    assert result and result["status"] == "completed"
    assert result["estimated_tokens"] == 30
    assert result["events"][1]["payload"]["rag_documents"] == ["guide.md"]
    serialized = str(result)
    assert "prompt" not in serialized.lower() or "prompt_chars" in serialized


def test_provider_registry_never_stores_secret_value(tmp_path: Path):
    control = EnterpriseStore(tmp_path / "enterprise.db")
    item = control.set_provider("demo", "Local", "ollama", "http://localhost:11434", "llama:3b", None, True)
    cloud = control.set_provider("demo", "Cloud", "openai-compatible", "https://llm.example.test", "model-a", "COMPAT_API_KEY", True)
    assert item["type"] == "ollama"
    assert cloud["api_key_env"] == "COMPAT_API_KEY"
    assert {provider["name"] for provider in control.providers("demo")} == {"Local", "Cloud"}
    assert control.remove_provider("demo", item["id"])


def test_anthropic_compatible_provider_is_accepted():
    provider = ProviderUpdate(name="Claude gateway", type="anthropic-compatible",
        base_url="https://gateway.example.test", model="custom-claude", api_key_env="ANTHROPIC_GATEWAY_KEY")
    assert provider.type == "anthropic-compatible"


def test_approval_can_only_be_claimed_once(tmp_path: Path):
    control = EnterpriseStore(tmp_path / "enterprise.db")
    tool = control.set_tool("demo", "Create ticket", "POST", "https://example.test/tickets", True, 5, 1000)
    approval = control.request_approval("demo", tool["id"], "alice", {"title": "Bug"})
    control.claim_approval("demo", approval["id"])
    with pytest.raises(Exception, match="déjà été traitée"):
        control.claim_approval("demo", approval["id"])
    decided = control.decide_approval("demo", approval["id"], "approved", "bob", {"status_code": 201})
    assert decided["status"] == "approved"


def test_tool_policy_precedence_and_default(tmp_path: Path):
    control = EnterpriseStore(tmp_path / "enterprise.db")
    direct = control.set_tool("demo", "Read weather", "GET", "https://example.test/weather", False, 5, 1000)
    guarded = control.set_tool("demo", "Create ticket", "POST", "https://example.test/tickets", True, 5, 1000)

    assert control.evaluate_tool_policy("demo", direct["id"])["effect"] == "allow"
    assert control.evaluate_tool_policy("demo", guarded["id"])["effect"] == "require_approval"

    control.set_policy("demo", "Allow weather", "allow", direct["id"], 900, True)
    control.set_policy("demo", "Review all", "require_approval", None, 100, True)
    assert control.evaluate_tool_policy("demo", direct["id"])["effect"] == "allow"

    denied = control.set_policy("demo", "Emergency stop", "deny", None, 1, True)
    decision = control.evaluate_tool_policy("demo", direct["id"])
    assert decision["effect"] == "deny"
    assert decision["policy_id"] == denied["id"]


def test_failed_tool_execution_does_not_leave_approval_processing(tmp_path: Path):
    control = EnterpriseStore(tmp_path / "enterprise.db")
    tool = control.set_tool("demo", "Create ticket", "POST", "https://example.test/tickets", True, 5, 1000)
    approval = control.request_approval("demo", tool["id"], "alice", {"title": "Bug"})
    control.claim_approval("demo", approval["id"])
    failed = control.fail_claimed_approval("demo", approval["id"], "bob", "Service indisponible")
    assert failed["status"] == "failed"
    assert failed["result"] == {"error": "Service indisponible"}


def test_mcp_sync_imports_only_declared_read_only_tools(tmp_path: Path):
    control = EnterpriseStore(tmp_path / "enterprise.db")
    server = control.set_mcp_server("demo", "Issues", "https://mcp.example.test/mcp", "MCP_KEY", True)
    imported = control.sync_mcp_tools("demo", server["id"], [
        {"name": "read_issue", "description": "Read one issue", "inputSchema": {"type": "object"},
         "annotations": {"readOnlyHint": True}},
        {"name": "delete_issue", "annotations": {"readOnlyHint": False}},
        {"name": "unclassified_tool"},
    ])
    assert [tool["action"] for tool in imported] == ["read_issue"]
    assert imported[0]["connector_type"] == "mcp"
    assert imported[0]["input_schema"] == {"type": "object"}


def test_mcp_sync_disables_tools_removed_upstream(tmp_path: Path):
    control = EnterpriseStore(tmp_path / "enterprise.db")
    server = control.set_mcp_server("demo", "Issues", "https://mcp.example.test/mcp", None, True)
    imported = control.sync_mcp_tools("demo", server["id"], [
        {"name": "read_issue", "annotations": {"readOnlyHint": True}},
    ])
    control.sync_mcp_tools("demo", server["id"], [])
    tool = next(item for item in control.tools("demo") if item["id"] == imported[0]["id"])
    assert tool["enabled"] == 0
