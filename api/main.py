"""Biscuits Focus API — dataset, training, evaluation and chat endpoints for the
Next.js management UI (web/). Not the model-serving API described in mission
section 36 (POST /v1/chat etc.) — this one is the internal tool for managing
the ML pipeline itself. Run with:

    uvicorn api.main:app --reload --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import chat, dataset, evaluation, experiments, jobs, projects, rag, system, training

app = FastAPI(title="Biscuits Focus — Management API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dataset.router)
app.include_router(experiments.router)
app.include_router(training.router)
app.include_router(evaluation.router)
app.include_router(jobs.router)
app.include_router(chat.router)
app.include_router(rag.router)
app.include_router(system.router)
app.include_router(projects.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
