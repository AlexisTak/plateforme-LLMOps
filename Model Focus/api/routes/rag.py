"""RAG document management + retrieval testing, scoped to one project.

Documents live under projects/<id>/rag/documents/<category>/*.md — category is
one of "methods", "research", "product" or "other". Upload accepts PDF, TXT and MD
(see rag/ingest.py). Reindexing runs as a background job (api/jobs.py) so
uploading many or large documents doesn't block the request or hit an HTTP
timeout. Every project has its own Chroma index — nothing here is shared.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from api.jobs import registry
from api.paths import project_dir
from api.schemas import (
    JobStatus,
    RagCategory,
    RagDocumentCreate,
    RagDocumentSummary,
    RagSearchRequest,
    RagSearchResult,
)
from rag import ingest
from rag.retriever import retrieve

VALID_CATEGORIES = set(get_args(RagCategory))

router = APIRouter(prefix="/api/projects/{project_id}/rag", tags=["rag"])

SAFE_MD_FILENAME = re.compile(r"^[a-zA-Z0-9_\-]+\.md$")


def _validate_category(category: str) -> str:
    if category not in VALID_CATEGORIES:
        raise HTTPException(400, f"category must be one of {sorted(VALID_CATEGORIES)}")
    return category


def _safe_md_path(project: Path, category: str, filename: str) -> Path:
    _validate_category(category)
    if not SAFE_MD_FILENAME.match(filename):
        raise HTTPException(400, "filename must match [a-zA-Z0-9_-]+.md — no paths, no other extensions")
    return project / "rag" / "documents" / category / filename


def _summarize(path: Path, category: str, reindex_job_id: str | None = None) -> RagDocumentSummary:
    text = path.read_text(encoding="utf-8")
    return RagDocumentSummary(
        filename=path.name,
        category=category,
        size_bytes=path.stat().st_size,
        char_count=len(text),
        preview=text.strip()[:200],
        reindex_job_id=reindex_job_id,
    )


def _trigger_auto_reindex(project: Path) -> str | None:
    job = registry.request_reindex(project)
    return job.job_id if job else None


@router.get("/documents", response_model=list[RagDocumentSummary])
def list_documents(project: Path = Depends(project_dir)):
    documents_dir = project / "rag" / "documents"
    documents_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    for path in sorted(documents_dir.glob("*/*.md")):
        summaries.append(_summarize(path, path.parent.name))
    return summaries


@router.post("/documents", response_model=RagDocumentSummary)
def create_document(body: RagDocumentCreate, project: Path = Depends(project_dir)):
    path = _safe_md_path(project, body.category, body.filename)
    if path.exists():
        raise HTTPException(409, f"{body.category}/{body.filename} already exists — delete it first or pick another name")
    if not body.content.strip():
        raise HTTPException(400, "content is empty")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body.content, encoding="utf-8")
    job_id = _trigger_auto_reindex(project)
    return _summarize(path, body.category, job_id)


@router.post("/documents/upload", response_model=RagDocumentSummary)
async def upload_document(project_id: str, file: UploadFile, category: str = Form("other")):
    project = project_dir(project_id)
    _validate_category(category)
    if not file.filename:
        raise HTTPException(400, "no filename provided")

    raw = await file.read()
    try:
        # PDF text extraction is CPU-bound and can take a while on large files —
        # run it off the event loop so it doesn't stall other requests (health
        # checks, other uploads, chat) for the duration.
        text = await run_in_threadpool(ingest.extract_text, file.filename, raw)
        basename = ingest.sanitize_basename(file.filename)
    except ingest.IngestError as e:
        raise HTTPException(400, str(e))

    category_dir = project / "rag" / "documents" / category
    category_dir.mkdir(parents=True, exist_ok=True)
    path = category_dir / basename
    if path.exists():
        # avoid silently clobbering an existing doc on a name collision — suffix instead
        i = 2
        while (category_dir / f"{path.stem}_{i}.md").exists():
            i += 1
        path = category_dir / f"{path.stem}_{i}.md"

    path.write_text(text, encoding="utf-8")
    job_id = _trigger_auto_reindex(project)
    return _summarize(path, category, job_id)


@router.delete("/documents/{category}/{filename}")
def delete_document(category: str, filename: str, project: Path = Depends(project_dir)):
    path = _safe_md_path(project, category, filename)
    if not path.exists():
        raise HTTPException(404, f"no such document: {category}/{filename}")
    path.unlink()
    job_id = _trigger_auto_reindex(project) if any((project / "rag" / "documents").glob("*/*.md")) else None
    return {"deleted": True, "reindex_job_id": job_id}


@router.post("/reindex", response_model=JobStatus)
def reindex(project: Path = Depends(project_dir)):
    if not any((project / "rag" / "documents").glob("*/*.md")):
        raise HTTPException(400, "no documents in rag/documents/ to index")
    job = registry.start_reindex(project)
    return JobStatus(job_id=job.job_id, kind="reindex", status=job.status, started_at=job.started_at, log_tail=[])


@router.post("/search", response_model=list[RagSearchResult])
def search(body: RagSearchRequest, project: Path = Depends(project_dir)):
    try:
        chunks = retrieve(body.query, project, top_k=body.top_k)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    return [RagSearchResult(chunk_id=c.chunk_id, doc_id=c.doc_id, category=c.category, text=c.text, score=c.score) for c in chunks]
