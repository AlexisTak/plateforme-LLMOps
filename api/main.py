"""OpenAgent API — dataset, training, evaluation and chat endpoints for the
Next.js management UI (web/). Not the model-serving API described in mission
section 36 (POST /v1/chat etc.) — this one is the internal tool for managing
the ML pipeline itself. Run with:

    uvicorn api.main:app --reload --port 8000
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from api.enterprise import actor_from_request, auth_mode, metrics, require_role, store
from api.jobs import registry
from api.paths import PROJECTS_DIR
from api.routes import (
    auth,
    chat,
    dataset,
    decision,
    enterprise,
    evaluation,
    experiments,
    jobs,
    opportunities,
    projects,
    rag,
    system,
    training,
)


def _bootstrap_admin() -> None:
    """F01 — first account for a fresh `login`-mode deployment (Docker, CI) without a
    shell: BISCUITS_BOOTSTRAP_ADMIN_EMAIL + _PASSWORD create it once, only while the
    users table is empty. Interactive setups use scripts/create_user.py instead."""
    email, password = os.getenv("BISCUITS_BOOTSTRAP_ADMIN_EMAIL"), os.getenv("BISCUITS_BOOTSTRAP_ADMIN_PASSWORD")
    if auth_mode() != "login" or not email or not password or store.user_count():
        return
    user = store.create_user(email, os.getenv("BISCUITS_BOOTSTRAP_ADMIN_NAME", "Administrateur"), "admin", password)
    store.audit("system", "auth.user.created", "user", user["id"], None, {"email": user["email"], "role": "admin", "bootstrap": True})
    logging.getLogger("openagent.auth").info("Compte administrateur initial créé pour %s", user["email"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    _bootstrap_admin()
    yield
    await run_in_threadpool(registry.shutdown)


app = FastAPI(title="OpenAgent — Management API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,  # the session cookie (F01) must ride along on cross-origin console calls
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def observability_and_audit(request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    started = time.perf_counter()
    # Login/logout/me are reachable without a session by construction; /me and
    # /password only need an actor, which the routes check themselves. Liveness/
    # readiness stay open for orchestrators. Everything else under /api/ needs an
    # authenticated actor even for GET — jobs logs, project lists, system health,
    # metrics and registry manifests are not public information.
    path = request.url.path
    exempt = path.startswith("/api/auth/") or path in {"/api/health", "/api/ready"}
    if path.startswith("/api/") and not exempt:
        minimum = "operator" if request.method in {"POST", "PUT", "PATCH", "DELETE"} else "viewer"
        try:
            require_role(actor_from_request(request), minimum)
        except HTTPException as exc:
            response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
            duration_ms = (time.perf_counter() - started) * 1000
            metrics.observe(request.method, response.status_code, duration_ms)
            response.headers["x-request-id"] = request_id
            return response
    parts = path.split("/")
    # Project membership is enforced for both URL shapes that carry a project id:
    # /api/projects/{id}/... and /api/enterprise/projects/{id}/... (registry, quota,
    # budget, deployment, tools...). Routes tighten the role further where needed.
    project_id = None
    if len(parts) > 3 and parts[2] == "projects":
        project_id = parts[3]
    elif len(parts) > 4 and parts[2] == "enterprise" and parts[3] == "projects":
        project_id = parts[4]
    if project_id:
        try:
            store.require_project_role(project_id, actor_from_request(request), "viewer")
        except HTTPException as exc:
            response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
            response.headers["x-request-id"] = request_id
            metrics.observe(request.method, response.status_code, (time.perf_counter() - started) * 1000)
            return response
    response = await call_next(request)
    duration_ms = (time.perf_counter() - started) * 1000
    metrics.observe(request.method, response.status_code, duration_ms)
    response.headers["x-request-id"] = request_id
    logging.getLogger("openagent.http").info(json.dumps({"request_id": request_id, "method": request.method,
        "path": request.url.path, "status": response.status_code, "duration_ms": round(duration_ms, 2)}))
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and response.status_code < 400 and not request.url.path.startswith("/api/enterprise"):
        try:
            current = actor_from_request(request)
            store.audit(current.id, f"http.{request.method.lower()}", "api", request.url.path, project_id,
                        {"status": response.status_code, "request_id": request_id})
        except Exception:
            logging.getLogger(__name__).exception("Impossible d’écrire l’audit")
    return response

class ApiV1AliasMiddleware:
    """/api/v1/* mirrors /api/* byte-for-byte — a stable prefix external SDKs and
    integrations can pin against (CLAUDE.md §18) without us maintaining two parallel
    implementations. Runs before routing, so every current and future /api/* endpoint
    is reachable under /api/v1/* automatically.
    ponytail: alias only, no independent v1/v2 behavior yet — split into real per-version
    routers the day an endpoint actually needs to behave differently across versions.
    Known limitation: the OpenAPI schema still lists paths under /api/*, not /api/v1/*,
    since this rewrite happens below FastAPI's routing/schema layer."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith("/api/v1/"):
            scope = {**scope, "path": "/api/" + scope["path"][len("/api/v1/"):]}
        await self.app(scope, receive, send)


app.add_middleware(ApiV1AliasMiddleware)

app.include_router(auth.router)
app.include_router(dataset.router)
app.include_router(experiments.router)
app.include_router(training.router)
app.include_router(evaluation.router)
app.include_router(jobs.router)
app.include_router(chat.router)
app.include_router(rag.router)
app.include_router(system.router)
app.include_router(projects.router)
app.include_router(decision.router)
app.include_router(enterprise.router)
app.include_router(opportunities.router)


@app.get("/api/health")
def health():
    """Liveness — the process is up and answering HTTP. Never checks
    dependencies, see /api/ready for that."""
    return {"status": "ok"}


@app.get("/api/ready")
def ready():
    """Readiness — the control plane's own dependencies (SQLite store, the
    projects/ directory) are actually reachable. Used by docker-compose's
    healthcheck so the web container waits for a genuinely usable API,
    not just a process that has started."""
    if not PROJECTS_DIR.is_dir():
        raise HTTPException(503, "projects directory unavailable")
    try:
        store.audits(limit=1)
    except Exception as exc:
        raise HTTPException(503, f"enterprise database unavailable: {exc}")
    return {"status": "ready"}
