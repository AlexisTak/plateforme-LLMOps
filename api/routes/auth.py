"""F01 — « Authentification locale sécurisée et fermeture de la création publique
de comptes ».

Active with BISCUITS_AUTH_MODE=login. Accounts live in the control-plane
SQLite (bcrypt hashes); a login opens a server-side session whose *hash* is
stored, and the raw token travels as an HttpOnly cookie (web console) or an
`Authorization: Bearer` header (scripts, SDK). There is deliberately no
self-service signup: accounts are created by an admin here, or by
scripts/create_user.py / the BISCUITS_BOOTSTRAP_ADMIN_* variables for the very
first one.

In `local` mode (the default, single implicit admin) and `proxy` mode these
routes still answer GET /me so the console can adapt, but login/logout are
meaningless there and say so.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from api.enterprise import (
    SESSION_COOKIE,
    SESSION_TTL_SECONDS,
    Actor,
    actor_from_request,
    auth_mode,
    require_role,
    session_token_from_request,
    store,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Brute-force throttle: 5 failures per (client, e-mail) in a 15-minute window, then
# 429 until the window slides. In-memory on purpose — one API process (CLAUDE.md
# §23-style guard, not a distributed rate limiter).
LOGIN_MAX_FAILURES = 5
LOGIN_WINDOW_SECONDS = 15 * 60
_failures: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_failures_lock = threading.Lock()


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    name: str = Field(min_length=1, max_length=200)
    role: str = Field(pattern=r"^(viewer|operator|reviewer|admin)$")
    password: str = Field(min_length=10, max_length=1024)


class UserUpdate(BaseModel):
    role: str | None = Field(default=None, pattern=r"^(viewer|operator|reviewer|admin)$")
    enabled: bool | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    password: str | None = Field(default=None, min_length=10, max_length=1024)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=10, max_length=1024)


def _client_key(request: Request, email: str) -> tuple[str, str]:
    host = request.client.host if request.client else "unknown"
    return host, email.strip().lower()


def _throttled(key: tuple[str, str]) -> bool:
    cutoff = time.monotonic() - LOGIN_WINDOW_SECONDS
    with _failures_lock:
        attempts = _failures[key]
        while attempts and attempts[0] < cutoff:
            attempts.popleft()
        return len(attempts) >= LOGIN_MAX_FAILURES


def _record_failure(key: tuple[str, str]) -> None:
    with _failures_lock:
        _failures[key].append(time.monotonic())


def _clear_failures(key: tuple[str, str]) -> None:
    with _failures_lock:
        _failures.pop(key, None)


def _set_session_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, token, max_age=SESSION_TTL_SECONDS, httponly=True, samesite="lax",
        secure=request.url.scheme == "https", path="/",
    )


def _require_login_mode() -> None:
    if auth_mode() != "login":
        raise HTTPException(409, "Comptes locaux inactifs — démarre l'API avec BISCUITS_AUTH_MODE=login")


@router.get("/me")
def me(request: Request):
    """Who am I, and which auth mode is the API in — the console reads this once
    at startup to decide whether to show the login screen."""
    mode = auth_mode()
    try:
        actor = actor_from_request(request)
    except HTTPException as exc:
        if exc.status_code == 401:
            return {"auth_mode": mode, "actor": None}
        raise
    return {"auth_mode": mode, "actor": actor.__dict__}


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response):
    _require_login_mode()
    if store.user_count() == 0:
        raise HTTPException(503, "Aucun compte — crée l'administrateur initial avec scripts/create_user.py")
    key = _client_key(request, body.email)
    if _throttled(key):
        raise HTTPException(429, "Trop de tentatives — réessaie dans quelques minutes")
    user = store.authenticate(body.email, body.password)
    if user is None:
        _record_failure(key)
        store.audit("anonymous", "auth.login.failed", "user", body.email.strip().lower(), None, {"client": key[0]})
        raise HTTPException(401, "E-mail ou mot de passe incorrect")
    _clear_failures(key)
    token = store.create_session(user["id"], client=key[0])
    _set_session_cookie(response, request, token)
    store.audit(user["id"], "auth.login", "user", user["id"], None, {"client": key[0]})
    # The token is also returned in the body for non-browser clients (Bearer usage).
    return {"actor": Actor(user["id"], user["email"], user["role"], user["name"]).__dict__, "token": token}


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response):
    token = session_token_from_request(request)
    if token:
        try:
            actor = actor_from_request(request)
            store.audit(actor.id, "auth.logout", "user", actor.id)
        except HTTPException:
            pass
        store.revoke_session(token)
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.post("/password", status_code=204)
def change_password(body: PasswordChange, request: Request, response: Response):
    _require_login_mode()
    actor = actor_from_request(request)
    if store.authenticate(actor.email, body.current_password) is None:
        raise HTTPException(403, "Mot de passe actuel incorrect")
    store.update_user(actor.id, password=body.new_password)  # revokes every session, including this one
    store.audit(actor.id, "auth.password.changed", "user", actor.id)
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/users")
def list_users(request: Request):
    _require_login_mode()
    require_role(actor_from_request(request), "admin")
    return store.users()


@router.post("/users", status_code=201)
def create_user(body: UserCreate, request: Request):
    """Admin-only — this is the only HTTP way to get an account (no public signup)."""
    _require_login_mode()
    current = actor_from_request(request)
    require_role(current, "admin")
    user = store.create_user(body.email, body.name, body.role, body.password)
    store.audit(current.id, "auth.user.created", "user", user["id"], None, {"email": user["email"], "role": user["role"]})
    return user


@router.patch("/users/{user_id}")
def update_user(user_id: str, body: UserUpdate, request: Request):
    _require_login_mode()
    current = actor_from_request(request)
    require_role(current, "admin")
    if user_id == current.id and (body.enabled is False or (body.role is not None and body.role != "admin")):
        raise HTTPException(409, "Tu ne peux pas te retirer ton propre accès administrateur")
    user = store.update_user(user_id, role=body.role, enabled=body.enabled, password=body.password, name=body.name)
    store.audit(current.id, "auth.user.updated", "user", user_id, None,
                {k: v for k, v in body.model_dump().items() if v is not None and k != "password"}
                | ({"password_reset": True} if body.password else {}))
    return user
