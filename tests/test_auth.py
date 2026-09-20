"""F01 — local login: accounts, sessions, throttling, admin-only account creation.

Store-level tests use an isolated EnterpriseStore; HTTP tests use the module-level
singleton (isolated per session by tests/conftest.py) with BISCUITS_AUTH_MODE=login
switched on through monkeypatch, so the default `local` mode of every other test
file is untouched."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.enterprise import EnterpriseStore

PASSWORD = "correct-horse-battery"


# --- store -------------------------------------------------------------------


def test_password_is_hashed_and_verified(tmp_path: Path):
    control = EnterpriseStore(tmp_path / "e.db")
    user = control.create_user("Alice@Example.com", "Alice", "admin", PASSWORD)
    assert "password_hash" not in user
    assert user["email"] == "alice@example.com"  # normalised
    assert control.authenticate("alice@example.com", PASSWORD)["id"] == user["id"]
    assert control.authenticate("alice@example.com", "wrong-password-1") is None
    assert control.authenticate("nobody@example.com", PASSWORD) is None


def test_create_user_validates_role_password_and_uniqueness(tmp_path: Path):
    control = EnterpriseStore(tmp_path / "e.db")
    with pytest.raises(HTTPException, match="Rôle inconnu"):
        control.create_user("a@x.test", "A", "superuser", PASSWORD)
    with pytest.raises(HTTPException, match="trop court"):
        control.create_user("a@x.test", "A", "viewer", "short")
    control.create_user("a@x.test", "A", "viewer", PASSWORD)
    with pytest.raises(HTTPException, match="existe déjà"):
        control.create_user("A@X.TEST", "A", "viewer", PASSWORD)


def test_session_round_trip_revocation_and_disable(tmp_path: Path):
    control = EnterpriseStore(tmp_path / "e.db")
    user = control.create_user("a@x.test", "A", "operator", PASSWORD)
    token = control.create_session(user["id"])
    actor = control.session_actor(token)
    assert (actor.id, actor.role) == (user["id"], "operator")
    assert control.session_actor("not-a-token") is None

    control.update_user(user["id"], enabled=False)
    assert control.session_actor(token) is None  # disabling kills live sessions
    control.update_user(user["id"], enabled=True)
    token = control.create_session(user["id"])
    control.revoke_session(token)
    assert control.session_actor(token) is None


def test_password_change_logs_every_session_out(tmp_path: Path):
    control = EnterpriseStore(tmp_path / "e.db")
    user = control.create_user("a@x.test", "A", "viewer", PASSWORD)
    token = control.create_session(user["id"])
    control.update_user(user["id"], password="another-long-password")
    assert control.session_actor(token) is None
    assert control.authenticate("a@x.test", "another-long-password") is not None


def test_expired_session_is_rejected(tmp_path: Path, monkeypatch):
    from api import enterprise

    control = EnterpriseStore(tmp_path / "e.db")
    user = control.create_user("a@x.test", "A", "viewer", PASSWORD)
    monkeypatch.setattr(enterprise, "SESSION_TTL_SECONDS", -1)
    token = control.create_session(user["id"])
    assert control.session_actor(token) is None


# --- routes ------------------------------------------------------------------


@pytest.fixture
def login_client(monkeypatch):
    from api.enterprise import store
    from api.routes import auth as auth_routes
    from api.routes import enterprise as enterprise_routes

    monkeypatch.setenv("BISCUITS_AUTH_MODE", "login")
    auth_routes._failures.clear()
    app = FastAPI()
    app.include_router(auth_routes.router)
    app.include_router(enterprise_routes.router)
    client = TestClient(app)
    admin = store.create_user(f"admin-{id(client)}@x.test", "Admin", "admin", PASSWORD)
    return client, store, admin


def _login(client, email, password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_login_sets_cookie_and_me_reflects_the_session(login_client):
    client, _, admin = login_client
    assert client.get("/api/auth/me").json() == {"auth_mode": "login", "actor": None}
    response = _login(client, admin["email"])
    assert response.status_code == 200
    assert "biscuits_session" in response.cookies
    assert "token" in response.json()
    me = client.get("/api/auth/me").json()  # TestClient keeps the cookie jar
    assert me["actor"]["email"] == admin["email"]
    assert me["actor"]["role"] == "admin"


def test_bearer_token_works_for_non_browser_clients(login_client):
    client, _, admin = login_client
    token = _login(client, admin["email"]).json()["token"]
    client.cookies.clear()
    assert client.get("/api/auth/me").json()["actor"] is None
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["actor"]["id"] == admin["id"]


def test_wrong_password_is_401_and_throttled_after_five_failures(login_client):
    client, _, admin = login_client
    for _ in range(5):
        assert _login(client, admin["email"], "wrong-password-x").status_code == 401
    assert _login(client, admin["email"], PASSWORD).status_code == 429  # even the right one, now


def test_unknown_email_gets_the_same_401(login_client):
    client, _, _ = login_client
    assert _login(client, "ghost@x.test").status_code == 401


def test_protected_routes_require_a_session(login_client):
    client, _, _ = login_client
    assert client.get("/api/enterprise/context").status_code == 401
    assert client.get("/api/auth/users").status_code == 401
    assert client.post("/api/auth/users", json={"email": "x@x.test", "name": "X", "role": "viewer",
                                                "password": PASSWORD}).status_code == 401  # no public signup


def test_only_admins_create_accounts(login_client):
    client, store, admin = login_client
    viewer = store.create_user(f"viewer-{id(client)}@x.test", "V", "viewer", PASSWORD)
    _login(client, viewer["email"])
    denied = client.post("/api/auth/users", json={"email": "new@x.test", "name": "N", "role": "viewer", "password": PASSWORD})
    assert denied.status_code == 403

    client.cookies.clear()
    _login(client, admin["email"])
    created = client.post("/api/auth/users", json={"email": f"new-{id(client)}@x.test", "name": "N", "role": "operator",
                                                   "password": PASSWORD})
    assert created.status_code == 201
    assert created.json()["role"] == "operator"
    assert "password_hash" not in created.json()


def test_disabled_account_cannot_log_in_and_loses_its_session(login_client):
    client, store, admin = login_client
    user = store.create_user(f"u-{id(client)}@x.test", "U", "viewer", PASSWORD)
    _login(client, user["email"])
    assert client.get("/api/auth/me").json()["actor"]["id"] == user["id"]
    store.update_user(user["id"], enabled=False)
    assert client.get("/api/auth/me").json()["actor"] is None
    assert _login(client, user["email"]).status_code == 401


def test_admin_cannot_lock_themselves_out(login_client):
    client, _, admin = login_client
    _login(client, admin["email"])
    assert client.patch(f"/api/auth/users/{admin['id']}", json={"enabled": False}).status_code == 409
    assert client.patch(f"/api/auth/users/{admin['id']}", json={"role": "viewer"}).status_code == 409


def test_logout_revokes_the_session(login_client):
    client, _, admin = login_client
    token = _login(client, admin["email"]).json()["token"]
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["actor"] is None


def test_change_own_password_needs_the_current_one(login_client):
    client, _, admin = login_client
    _login(client, admin["email"])
    assert client.post("/api/auth/password", json={"current_password": "nope-nope-nope",
                                                   "new_password": "brand-new-password"}).status_code == 403
    assert client.post("/api/auth/password", json={"current_password": PASSWORD,
                                                   "new_password": "brand-new-password"}).status_code == 204
    assert client.get("/api/auth/me").json()["actor"] is None  # logged out everywhere
    assert _login(client, admin["email"], "brand-new-password").status_code == 200


def test_login_without_any_account_points_to_the_bootstrap_script(monkeypatch, tmp_path: Path):
    from api import enterprise
    from api.routes import auth as auth_routes

    monkeypatch.setenv("BISCUITS_AUTH_MODE", "login")
    monkeypatch.setattr(enterprise, "store", EnterpriseStore(tmp_path / "empty.db"))
    monkeypatch.setattr(auth_routes, "store", enterprise.store)
    app = FastAPI()
    app.include_router(auth_routes.router)
    response = TestClient(app).post("/api/auth/login", json={"email": "a@x.test", "password": PASSWORD})
    assert response.status_code == 503
    assert "create_user" in response.json()["detail"]


def test_bootstrap_env_creates_the_first_admin_once(monkeypatch, tmp_path: Path):
    from api import enterprise, main

    fresh = EnterpriseStore(tmp_path / "boot.db")
    monkeypatch.setattr(main, "store", fresh)
    monkeypatch.setenv("BISCUITS_AUTH_MODE", "login")
    monkeypatch.setenv("BISCUITS_BOOTSTRAP_ADMIN_EMAIL", "boot@x.test")
    monkeypatch.setenv("BISCUITS_BOOTSTRAP_ADMIN_PASSWORD", PASSWORD)
    main._bootstrap_admin()
    main._bootstrap_admin()  # idempotent: users table no longer empty
    users = fresh.users()
    assert [u["email"] for u in users] == ["boot@x.test"]
    assert users[0]["role"] == "admin"
    assert enterprise.auth_mode() == "login"


def test_local_mode_is_untouched(monkeypatch):
    from api.routes import auth as auth_routes

    monkeypatch.setenv("BISCUITS_AUTH_MODE", "local")
    app = FastAPI()
    app.include_router(auth_routes.router)
    client = TestClient(app)
    me = client.get("/api/auth/me").json()
    assert me["auth_mode"] == "local"
    assert me["actor"]["id"] == "local-admin"
    assert client.post("/api/auth/login", json={"email": "a@x.test", "password": PASSWORD}).status_code == 409
