"""F01 — local login: accounts, sessions, throttling, admin-only account creation.

Store-level tests use an isolated EnterpriseStore; HTTP tests use the module-level
singleton (isolated per session by tests/conftest.py) with BISCUITS_AUTH_MODE=login
switched on through monkeypatch, so the default `local` mode of every other test
file is untouched."""

from __future__ import annotations

import uuid
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
    assert client.get("/api/auth/me").json() == {"auth_mode": "login", "actor": None, "setup_required": False}
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
    assert "premier lancement" in response.json()["detail"]
    assert "create_user" in response.json()["detail"]


# --- first-run setup ----------------------------------------------------------


@pytest.fixture
def empty_login_app(monkeypatch, tmp_path: Path):
    """login mode over an empty control plane: the state right after a fresh install."""
    from api import enterprise
    from api.routes import auth as auth_routes

    monkeypatch.setenv("BISCUITS_AUTH_MODE", "login")
    fresh = EnterpriseStore(tmp_path / "fresh.db")
    monkeypatch.setattr(enterprise, "store", fresh)
    monkeypatch.setattr(auth_routes, "store", fresh)
    app = FastAPI()
    app.include_router(auth_routes.router)
    return app, fresh


FIRST_ADMIN = {"email": "owner@x.test", "name": "Owner", "password": PASSWORD}


def test_first_run_setup_creates_admin_and_opens_session(empty_login_app):
    app, fresh = empty_login_app
    client = TestClient(app, client=("127.0.0.1", 50000))
    assert client.get("/api/auth/me").json() == {"auth_mode": "login", "actor": None, "setup_required": True}

    response = client.post("/api/auth/setup", json=FIRST_ADMIN)
    assert response.status_code == 201
    assert "biscuits_session" in response.cookies
    me = client.get("/api/auth/me").json()
    assert me["setup_required"] is False
    assert (me["actor"]["email"], me["actor"]["role"]) == ("owner@x.test", "admin")
    assert [e["action"] for e in fresh.audits()][:2] == ["auth.login", "auth.user.created"]


def test_first_run_setup_works_only_once(empty_login_app):
    app, fresh = empty_login_app
    client = TestClient(app, client=("127.0.0.1", 50000))
    assert client.post("/api/auth/setup", json=FIRST_ADMIN).status_code == 201
    second = client.post("/api/auth/setup", json={**FIRST_ADMIN, "email": "intruder@x.test"})
    assert second.status_code == 409
    assert [u["email"] for u in fresh.users()] == ["owner@x.test"]


def test_first_run_setup_is_refused_when_accounts_already_exist(empty_login_app):
    app, fresh = empty_login_app
    fresh.create_user("existing@x.test", "Existing", "viewer", PASSWORD)
    client = TestClient(app, client=("127.0.0.1", 50000))
    assert client.get("/api/auth/me").json()["setup_required"] is False
    assert client.post("/api/auth/setup", json=FIRST_ADMIN).status_code == 409
    assert len(fresh.users()) == 1


@pytest.mark.parametrize("client_addr, headers", [
    (("192.168.1.20", 50000), {}),                       # another machine on the LAN
    (("127.0.0.1", 50000), {"X-Forwarded-For": "203.0.113.9"}),  # local reverse proxy relaying a remote caller
    (("127.0.0.1", 50000), {"Forwarded": "for=203.0.113.9"}),
    (("testclient", 50000), {}),                         # not an IP at all
])
def test_first_run_setup_only_from_the_host_itself(empty_login_app, client_addr, headers):
    app, fresh = empty_login_app
    response = TestClient(app, client=client_addr).post("/api/auth/setup", json=FIRST_ADMIN, headers=headers)
    assert response.status_code == 403
    assert fresh.user_count() == 0


def test_first_run_setup_accepts_ipv6_loopback(empty_login_app):
    app, _ = empty_login_app
    assert TestClient(app, client=("::1", 50000)).post("/api/auth/setup", json=FIRST_ADMIN).status_code == 201


def test_first_run_setup_validates_input(empty_login_app):
    app, fresh = empty_login_app
    client = TestClient(app, client=("127.0.0.1", 50000))
    assert client.post("/api/auth/setup", json={**FIRST_ADMIN, "password": "short"}).status_code == 422
    assert client.post("/api/auth/setup", json={**FIRST_ADMIN, "email": "not-an-email"}).status_code == 422
    assert fresh.user_count() == 0


def test_first_run_setup_is_login_mode_only(monkeypatch):
    from api.routes import auth as auth_routes

    monkeypatch.setenv("BISCUITS_AUTH_MODE", "local")
    app = FastAPI()
    app.include_router(auth_routes.router)
    client = TestClient(app, client=("127.0.0.1", 50000))
    assert client.get("/api/auth/me").json()["setup_required"] is False
    assert client.post("/api/auth/setup", json=FIRST_ADMIN).status_code == 409


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


# --- project membership from accounts ("login" mode) -----------------------------

PROJECT = "assistant"  # tracked demo project, always present


def _new_account(client, role="operator"):
    email = f"member-{uuid.uuid4().hex[:12]}@x.test"
    user = client.post("/api/auth/users", json={"email": email, "name": "Member", "role": role, "password": PASSWORD})
    assert user.status_code == 201
    return user.json()


def test_member_added_by_account_id_gets_access(login_client):
    client, store, admin = login_client
    _login(client, admin["email"])
    member = _new_account(client)

    member_client = TestClient(client.app)
    _login(member_client, member["email"])
    assert member_client.get(f"/api/enterprise/projects/{PROJECT}/members").status_code == 403

    candidates = client.get(f"/api/enterprise/projects/{PROJECT}/member-candidates").json()
    assert member["id"] in {c["id"] for c in candidates}
    added = client.put(f"/api/enterprise/projects/{PROJECT}/members",
                       json={"actor_id": member["id"], "email": "spoofed@x.test", "name": "Spoofed", "role": "viewer"})
    assert added.status_code == 200
    assert (added.json()["email"], added.json()["name"]) == (member["email"], "Member")  # identity from the account
    assert member_client.get(f"/api/enterprise/projects/{PROJECT}/members").status_code == 200

    client.delete(f"/api/enterprise/projects/{PROJECT}/members/{member['id']}")
    assert member_client.get(f"/api/enterprise/projects/{PROJECT}/members").status_code == 403


def test_member_must_be_an_existing_enabled_account(login_client):
    client, store, admin = login_client
    _login(client, admin["email"])
    body = {"email": "x@x.test", "name": "X", "role": "viewer"}
    # the old console keyed members on the e-mail: nobody can ever log in as that actor id
    assert client.put(f"/api/enterprise/projects/{PROJECT}/members", json={**body, "actor_id": "x@x.test"}).status_code == 400
    disabled = _new_account(client)
    client.patch(f"/api/auth/users/{disabled['id']}", json={"enabled": False})
    assert client.put(f"/api/enterprise/projects/{PROJECT}/members", json={**body, "actor_id": disabled["id"]}).status_code == 400
    assert disabled["id"] not in {c["id"] for c in client.get(f"/api/enterprise/projects/{PROJECT}/member-candidates").json()}


def test_member_candidates_need_project_admin(login_client):
    client, store, admin = login_client
    _login(client, admin["email"])
    member = _new_account(client)
    client.put(f"/api/enterprise/projects/{PROJECT}/members",
               json={"actor_id": member["id"], "email": member["email"], "name": "Member", "role": "operator"})
    member_client = TestClient(client.app)
    _login(member_client, member["email"])
    assert member_client.get(f"/api/enterprise/projects/{PROJECT}/member-candidates").status_code == 403
    client.delete(f"/api/enterprise/projects/{PROJECT}/members/{member['id']}")
