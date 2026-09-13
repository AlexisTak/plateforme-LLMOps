"""Biscuits Focus API — dataset, training, evaluation and chat endpoints for the
Next.js management UI (web/). Not the model-serving API described in mission
section 36 (POST /v1/chat etc.) — this one is the internal tool for managing
the ML pipeline itself. Run with:

    uvicorn api.main:app --reload --port 8000
"""

from __future__ import annotations
from contextlib import asynccontextmanager
import json
import logging
import time
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from api.jobs import registry

from api.enterprise import actor_from_request, metrics, require_role, store
from api.routes import chat, dataset, enterprise, evaluation, experiments, jobs, projects, rag, system, training

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await run_in_threadpool(registry.shutdown)


app = FastAPI(title="Biscuits Focus — Management API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def observability_and_audit(request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    started = time.perf_counter()
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        try:
            require_role(actor_from_request(request), "operator")
        except HTTPException as exc:
            response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
            duration_ms = (time.perf_counter() - started) * 1000
            metrics.observe(request.method, response.status_code, duration_ms)
            response.headers["x-request-id"] = request_id
            return response
    parts = request.url.path.split("/")
    if len(parts) > 3 and parts[2] == "projects":
        try:
            store.require_project_role(parts[3], actor_from_request(request), "viewer")
        except HTTPException as exc:
            response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
            response.headers["x-request-id"] = request_id
            metrics.observe(request.method, response.status_code, (time.perf_counter() - started) * 1000)
            return response
    response = await call_next(request)
    duration_ms = (time.perf_counter() - started) * 1000
    metrics.observe(request.method, response.status_code, duration_ms)
    response.headers["x-request-id"] = request_id
    logging.getLogger("biscuits.http").info(json.dumps({"request_id": request_id, "method": request.method,
        "path": request.url.path, "status": response.status_code, "duration_ms": round(duration_ms, 2)}))
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and response.status_code < 400 and not request.url.path.startswith("/api/enterprise"):
        try:
            current = actor_from_request(request)
            project_id = parts[3] if len(parts) > 3 and parts[2] == "projects" else None
            store.audit(current.id, f"http.{request.method.lower()}", "api", request.url.path, project_id,
                        {"status": response.status_code, "request_id": request_id})
        except Exception:
            logging.getLogger(__name__).exception("Impossible d’écrire l’audit")
    return response

app.include_router(dataset.router)
app.include_router(experiments.router)
app.include_router(training.router)
app.include_router(evaluation.router)
app.include_router(jobs.router)
app.include_router(chat.router)
app.include_router(rag.router)
app.include_router(system.router)
app.include_router(projects.router)
app.include_router(enterprise.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
