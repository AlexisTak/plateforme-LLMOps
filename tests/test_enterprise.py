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


def test_registry_entry_carries_adapter_quantization_and_artifacts(tmp_path: Path):
    control = EnterpriseStore(tmp_path / "enterprise.db")
    actor = Actor("alice", "alice@example.test", "admin", "Alice")
    item = control.create_version(
        "demo", "1.0.0", "org/model", "v1", None, actor, "ready",
        adapter="experiment_003", quantization="q4_K_M", rag_version="rag-2026-09-15",
        environment="staging", artifacts={"models/adapters/experiment_003/adapter_model.safetensors": {"sha256": "abc"}},
    )
    assert item["adapter"] == "experiment_003"
    assert item["quantization"] == "q4_K_M"
    assert item["rag_version"] == "rag-2026-09-15"
    assert item["environment"] == "staging"
    assert item["artifacts"] == {"models/adapters/experiment_003/adapter_model.safetensors": {"sha256": "abc"}}

    # a version created before this migration (no adapter/quantization/artifacts
    # supplied) must still read back cleanly with sane defaults
    bare = control.create_version("demo", "1.0.1", "org/model", "v1", None, actor, "")
    assert bare["adapter"] is None
    assert bare["environment"] == "local"
    assert bare["artifacts"] == {}

    listed = {v["id"]: v for v in control.versions("demo")}
    assert listed[item["id"]]["adapter"] == "experiment_003"


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


def test_critical_risk_tool_is_always_gated_even_with_allow_policy(tmp_path: Path):
    control = EnterpriseStore(tmp_path / "enterprise.db")
    tool = control.set_tool("demo", "Drop table", "POST", "https://example.test/drop", False, 5, 1000, "critical")
    # No policy at all: falls back to the tool's own approval_required (False here), but risk
    # level still forces the gate — nothing critical should ever auto-execute.
    assert control.evaluate_tool_policy("demo", tool["id"])["effect"] == "require_approval"

    control.set_policy("demo", "Allow everything", "allow", tool["id"], 900, True)
    decision = control.evaluate_tool_policy("demo", tool["id"])
    assert decision["effect"] == "require_approval"
    assert "risque critique" in decision["reason"]

    # An explicit deny still wins over the critical-risk gate.
    denied = control.set_policy("demo", "Block drop", "deny", tool["id"], 950, True)
    decision = control.evaluate_tool_policy("demo", tool["id"])
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


def test_execution_export_is_versioned_json(monkeypatch, tmp_path: Path):
    from fastapi import FastAPI
    from api.paths import project_dir
    from api.routes import enterprise

    project = tmp_path / "demo"
    project.mkdir()
    detail = {"id": "run-1", "project_id": "demo", "events": [
        {"seq": 1, "type": "execution.started", "payload": {"model": "local"}},
    ]}
    monkeypatch.setattr(enterprise.store, "execution", lambda project_id, execution_id: detail)
    app = FastAPI()
    app.include_router(enterprise.router)
    app.dependency_overrides[project_dir] = lambda: project
    response = TestClient(app).get("/api/enterprise/projects/demo/executions/run-1/export")
    assert response.status_code == 200
    assert response.json() == {"schema_version": 1, "execution": detail}
    assert response.headers["content-disposition"] == 'attachment; filename="openagent-execution-run-1.json"'


def test_registry_sbom_reports_provenance_and_dependencies(monkeypatch, tmp_path: Path):
    from fastapi import FastAPI
    from api.paths import project_dir
    from api.routes import enterprise

    project = tmp_path / "demo"
    project.mkdir()
    isolated_store = EnterpriseStore(tmp_path / "enterprise.db")
    monkeypatch.setattr(enterprise, "store", isolated_store)
    actor = Actor("alice", "alice@example.test", "admin", "Alice")
    item = isolated_store.create_version(
        "demo", "1.0.0", "org/model", "v1", None, actor, "ready",
        adapter="experiment_003", artifacts={"models/adapters/experiment_003/adapter_model.safetensors": {"sha256": "abc"}},
    )
    monkeypatch.setattr(enterprise, "ROOT", tmp_path)
    (tmp_path / "requirements.txt").write_text("# comment\ntorch==2.5.0\ninvalid-line-without-pin\nfastapi==0.115.0\n", encoding="utf-8")

    app = FastAPI()
    app.include_router(enterprise.router)
    app.dependency_overrides[project_dir] = lambda: project
    response = TestClient(app).get(f"/api/enterprise/projects/demo/registry/{item['id']}/sbom")
    assert response.status_code == 200
    body = response.json()
    assert body["schema"] == "biscuits-sbom-1"
    assert body["model_version"]["adapter"] == "experiment_003"
    assert body["artifacts"] == item["artifacts"]
    assert {"name": "torch", "version": "2.5.0"} in body["python_dependencies"]
    assert len(body["python_dependencies"]) == 2


def test_registry_sbom_404_for_unknown_version(monkeypatch, tmp_path: Path):
    from fastapi import FastAPI
    from api.paths import project_dir
    from api.routes import enterprise

    project = tmp_path / "demo"
    project.mkdir()
    monkeypatch.setattr(enterprise, "store", EnterpriseStore(tmp_path / "enterprise.db"))
    app = FastAPI()
    app.include_router(enterprise.router)
    app.dependency_overrides[project_dir] = lambda: project
    response = TestClient(app).get("/api/enterprise/projects/demo/registry/nope/sbom")
    assert response.status_code == 404


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


def _restore_client(monkeypatch, tmp_path: Path, source: Path) -> tuple[TestClient, Path]:
    from fastapi import FastAPI
    from api.paths import project_dir
    from api.routes import enterprise

    projects_root = tmp_path / "projects_root"
    projects_root.mkdir()
    monkeypatch.setattr(enterprise, "PROJECTS_DIR", projects_root)

    app = FastAPI()
    app.include_router(enterprise.router)
    app.dependency_overrides[project_dir] = lambda: source
    return TestClient(app), projects_root


def test_backup_restore_round_trip_preserves_files(monkeypatch, tmp_path: Path):
    source = tmp_path / "source"
    (source / "datasets" / "core").mkdir(parents=True)
    (source / "datasets" / "core" / "a.jsonl").write_text('{"id":"1","messages":[]}\n', encoding="utf-8")
    (source / "meta.json").write_text('{"id": "source"}', encoding="utf-8")

    client, projects_root = _restore_client(monkeypatch, tmp_path, source)

    backup = client.get("/api/enterprise/projects/source/backup")
    assert backup.status_code == 200

    restored = client.post(
        "/api/enterprise/projects/restored-copy/restore",
        files={"file": ("backup.zip", backup.content, "application/zip")},
    )
    assert restored.status_code == 201
    assert restored.json() == {"restored": True, "project_id": "restored-copy", "files": 2}

    restored_file = projects_root / "restored-copy" / "datasets" / "core" / "a.jsonl"
    assert restored_file.read_text(encoding="utf-8") == (source / "datasets" / "core" / "a.jsonl").read_text(encoding="utf-8")
    assert (projects_root / "restored-copy" / "meta.json").exists()


def test_restore_refuses_to_overwrite_an_existing_project(monkeypatch, tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "meta.json").write_text('{"id": "source"}', encoding="utf-8")
    client, projects_root = _restore_client(monkeypatch, tmp_path, source)
    backup = client.get("/api/enterprise/projects/source/backup")

    (projects_root / "already-there").mkdir()
    response = client.post(
        "/api/enterprise/projects/already-there/restore",
        files={"file": ("backup.zip", backup.content, "application/zip")},
    )
    assert response.status_code == 409
    assert not (projects_root / "already-there" / "meta.json").exists()


def test_restore_rejects_tampered_archive_and_cleans_up(monkeypatch, tmp_path: Path):
    import io
    import zipfile

    source = tmp_path / "source"
    source.mkdir()
    (source / "meta.json").write_text('{"id": "source"}', encoding="utf-8")
    client, projects_root = _restore_client(monkeypatch, tmp_path, source)
    backup = client.get("/api/enterprise/projects/source/backup")

    original = zipfile.ZipFile(io.BytesIO(backup.content))
    tampered = io.BytesIO()
    with zipfile.ZipFile(tampered, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in original.namelist():
            data = original.read(name)
            if name.endswith("meta.json") and not name.endswith("BACKUP_MANIFEST.json"):
                data = b'{"id": "tampered"}'
            archive.writestr(name, data)

    response = client.post(
        "/api/enterprise/projects/tampered-copy/restore",
        files={"file": ("backup.zip", tampered.getvalue(), "application/zip")},
    )
    assert response.status_code == 409
    assert not (projects_root / "tampered-copy").exists()
