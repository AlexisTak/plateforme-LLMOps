"""Negative authorization tests pinned to AUDIT.md §2.1/§2.2 — every route under
/api/* (except auth/health/ready) needs an authenticated actor even for GET,
enterprise project routes enforce membership, and project-configured outbound
URLs can't reach the server's own network."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api import outbound

PROXY = {"BISCUITS_AUTH_MODE": "proxy", "BISCUITS_PROXY_SECRET": "test-secret"}


def _headers(actor_id: str, role: str) -> dict[str, str]:
    return {
        "x-biscuits-proxy-secret": "test-secret", "x-biscuits-user-id": actor_id,
        "x-biscuits-user-email": f"{actor_id}@example.test", "x-biscuits-role": role,
    }


@pytest.fixture
def login_client(monkeypatch):
    monkeypatch.setenv("BISCUITS_AUTH_MODE", "login")
    from api.main import app
    return TestClient(app)


@pytest.fixture
def proxy_client(monkeypatch):
    for key, value in PROXY.items():
        monkeypatch.setenv(key, value)
    from api.main import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# Default mode + GET routes now require an actor


def test_default_auth_mode_is_login_not_local(monkeypatch):
    monkeypatch.delenv("BISCUITS_AUTH_MODE", raising=False)
    from api.enterprise import auth_mode
    assert auth_mode() == "login"


@pytest.mark.parametrize("path", [
    "/api/jobs",
    "/api/projects",
    "/api/system/health",
    "/api/enterprise/metrics",
    "/api/enterprise/metrics/prometheus",
])
def test_get_routes_reject_anonymous_in_login_mode(login_client, path):
    response = login_client.get(path)
    assert response.status_code == 401, (path, response.text)


@pytest.mark.parametrize("path", ["/api/health", "/api/ready"])
def test_liveness_and_readiness_stay_open(login_client, path):
    assert login_client.get(path).status_code in (200, 503)


def test_login_route_stays_reachable_without_session(login_client):
    # The route itself answers (401 wrong credentials, 503 no account yet) — never a
    # middleware 401 before it. Distinguish by the detail: the middleware says
    # "Connexion requise".
    response = login_client.post("/api/auth/login", json={"email": "nobody@example.test", "password": "x"})
    assert response.status_code in (400, 401, 409, 422, 503)
    assert response.json().get("detail") != "Connexion requise"


# ---------------------------------------------------------------------------
# Enterprise project routes enforce membership (registry was cross-project before)


def test_enterprise_project_routes_require_membership(proxy_client, tmp_path, monkeypatch):
    from api import paths
    from api.enterprise import store

    monkeypatch.setattr(paths, "PROJECTS_DIR", tmp_path)
    project = tmp_path / "authz-registry-a"
    project.mkdir()
    (project / "meta.json").write_text('{"base_model": "test-model"}', encoding="utf-8")
    store.set_member("authz-registry-a", "owner", "owner@example.test", "Owner", "admin")

    stranger = _headers("stranger", "operator")  # global operator, not a member
    assert proxy_client.get("/api/enterprise/projects/authz-registry-a/registry", headers=stranger).status_code == 403
    assert proxy_client.post(
        "/api/enterprise/projects/authz-registry-a/registry", headers=stranger, json={"version": "v1", "notes": ""},
    ).status_code == 403

    member = _headers("owner", "admin")
    assert proxy_client.get("/api/enterprise/projects/authz-registry-a/registry", headers=member).status_code == 200


def test_registry_create_needs_operator_on_the_project(proxy_client, tmp_path, monkeypatch):
    from api import paths
    from api.enterprise import store

    monkeypatch.setattr(paths, "PROJECTS_DIR", tmp_path)
    project = tmp_path / "authz-registry-b"
    project.mkdir()
    (project / "meta.json").write_text('{"base_model": "test-model"}', encoding="utf-8")
    store.set_member("authz-registry-b", "reader", "reader@example.test", "Reader", "viewer")

    # Global operator but only viewer on this project: can list, cannot create.
    reader = _headers("reader", "operator")
    assert proxy_client.get("/api/enterprise/projects/authz-registry-b/registry", headers=reader).status_code == 200
    assert proxy_client.post(
        "/api/enterprise/projects/authz-registry-b/registry", headers=reader, json={"version": "v1", "notes": ""},
    ).status_code == 403


# ---------------------------------------------------------------------------
# Outbound URL policy (SSRF)


def _stub_resolve(monkeypatch, address: str):
    monkeypatch.setattr(outbound, "_resolve", lambda host, port: {address})


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.5", "192.168.1.20", "169.254.169.254", "::1", "0.0.0.0"])
def test_outbound_rejects_internal_addresses(monkeypatch, address):
    _stub_resolve(monkeypatch, address)
    with pytest.raises(HTTPException) as exc:
        outbound.validate_outbound_url("http://tool.example.test/hook")
    assert exc.value.status_code == 400


def test_outbound_accepts_public_address(monkeypatch):
    _stub_resolve(monkeypatch, "93.184.216.34")
    assert outbound.validate_outbound_url("https://tool.example.test/hook/") == "https://tool.example.test/hook"


def test_outbound_allowlist_keeps_local_ollama(monkeypatch):
    _stub_resolve(monkeypatch, "127.0.0.1")
    assert outbound.validate_outbound_url("http://127.0.0.1:11434") == "http://127.0.0.1:11434"
    assert outbound.validate_outbound_url("http://localhost:11434/") == "http://localhost:11434"
    with pytest.raises(HTTPException):
        outbound.validate_outbound_url("http://127.0.0.1:8000")  # same host, other port: not allowlisted


def test_outbound_allowlist_is_configurable(monkeypatch):
    _stub_resolve(monkeypatch, "10.1.2.3")
    monkeypatch.setenv("BISCUITS_OUTBOUND_ALLOW_PRIVATE", "intranet.corp:8443")
    assert outbound.validate_outbound_url("https://intranet.corp:8443/api") == "https://intranet.corp:8443/api"


def test_offline_mode_blocks_public_hosts(monkeypatch):
    monkeypatch.setenv("BISCUITS_OFFLINE", "1")
    _stub_resolve(monkeypatch, "93.184.216.34")
    with pytest.raises(HTTPException) as exc:
        outbound.validate_outbound_url("https://api.anthropic.test")
    assert exc.value.status_code == 403


def test_offline_mode_keeps_local_ollama(monkeypatch):
    monkeypatch.setenv("BISCUITS_OFFLINE", "1")
    _stub_resolve(monkeypatch, "127.0.0.1")
    assert outbound.validate_outbound_url("http://localhost:11434/") == "http://localhost:11434"
    with pytest.raises(HTTPException):
        outbound.validate_outbound_url("http://127.0.0.1:8000")  # loopback but not allowlisted


def test_offline_mode_rejects_allowlisted_lan_host(monkeypatch):
    # An allowlisted intranet service is still off-machine: offline means loopback only.
    monkeypatch.setenv("BISCUITS_OFFLINE", "1")
    monkeypatch.setenv("BISCUITS_OUTBOUND_ALLOW_PRIVATE", "intranet.corp:8443,localhost:11434")
    _stub_resolve(monkeypatch, "10.1.2.3")
    with pytest.raises(HTTPException):
        outbound.validate_outbound_url("https://intranet.corp:8443/api")
    # A hostname that is allowlisted as "localhost" but resolves elsewhere is refused too.
    with pytest.raises(HTTPException):
        outbound.validate_outbound_url("http://localhost:11434")


@pytest.mark.parametrize("url", ["ftp://x.test", "file:///etc/passwd", "http://", "http://user:pw@x.test", "not a url"])
def test_outbound_rejects_bad_schemes_and_credentials(monkeypatch, url):
    _stub_resolve(monkeypatch, "93.184.216.34")
    with pytest.raises(HTTPException):
        outbound.validate_outbound_url(url)


def test_outbound_unresolvable_host_is_rejected(monkeypatch):
    monkeypatch.setattr(outbound, "_resolve", lambda host, port: set())
    with pytest.raises(HTTPException) as exc:
        outbound.validate_outbound_url("http://does-not-exist.example.test")
    assert exc.value.status_code == 400


def test_tool_execution_revalidates_stored_url(proxy_client, tmp_path, monkeypatch):
    """A tool registered before the policy (or via a host that later resolves
    privately) must still be blocked at execution time."""
    from api import paths
    from api.enterprise import store

    monkeypatch.setattr(paths, "PROJECTS_DIR", tmp_path)
    project = tmp_path / "authz-ssrf"
    project.mkdir()
    (project / "meta.json").write_text('{"base_model": "test-model"}', encoding="utf-8")
    store.set_member("authz-ssrf", "op", "op@example.test", "Op", "admin")
    tool = store.set_tool("authz-ssrf", "meta", "GET", "http://169.254.169.254/latest/meta-data", False, 5, 4096)

    _stub_resolve(monkeypatch, "169.254.169.254")
    calls = []
    monkeypatch.setattr("api.routes.enterprise.requests.get", lambda *a, **k: calls.append(a) or (_ for _ in ()).throw(AssertionError("must not be called")))
    response = proxy_client.post(
        f"/api/enterprise/projects/authz-ssrf/tools/{tool['id']}/execute", headers=_headers("op", "admin"),
        json={"arguments": {}},
    )
    assert response.status_code == 400, response.text
    assert calls == []


# ---------------------------------------------------------------------------
# CORS must wrap the auth middleware (the web console is cross-origin: :3000 -> :8000)

CONSOLE = "http://localhost:3000"


def test_cors_preflight_is_not_blocked_by_auth(login_client):
    # Browsers never send cookies on preflight: a 401 here broke every console call in login mode.
    response = login_client.options("/api/projects", headers={
        "Origin": CONSOLE, "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "content-type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == CONSOLE
    assert response.headers["access-control-allow-credentials"] == "true"


def test_unauthenticated_401_carries_cors_headers(login_client):
    # Without them the console sees a network error and can't show the login screen.
    response = login_client.get("/api/projects", headers={"Origin": CONSOLE})
    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == CONSOLE
