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

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from starlette.concurrency import run_in_threadpool

from api.enterprise import ROLES, Actor, actor_from_request, store
from api.jobs import registry
from api.paths import project_dir
from api.schemas import (
    JobStatus,
    RagCategory,
    RagCategoryAcl,
    RagCategoryAclUpdate,
    RagDocumentCreate,
    RagDocumentSummary,
    RagEvalQuery,
    RagEvalResult,
    RagSearchRequest,
    RagSearchResult,
)
from rag import evaluation as rag_evaluation
from rag import ingest
from rag.retriever import retrieve

VALID_CATEGORIES = set(get_args(RagCategory))

router = APIRouter(prefix="/api/projects/{project_id}/rag", tags=["rag"])

SAFE_MD_FILENAME = re.compile(r"^[a-zA-Z0-9_\-]+\.md$")


def _validate_category(category: str) -> str:
    if category not in VALID_CATEGORIES:
        raise HTTPException(400, f"category must be one of {sorted(VALID_CATEGORIES)}")
    return category


def _require_category_role(project_id: str, actor: Actor, category: str, floor: str = "viewer") -> str:
    """F07 "droits de l'utilisateur" — a project role check (like every other route
    already does) plus a per-category floor on top of it (api.enterprise.EnterpriseStore
    .rag_category_acls), so a project member can still be kept out of one category's
    documents/search results. Returns the caller's resolved project role."""
    store.require_project_role(project_id, actor, floor)
    role = store.project_role(project_id, actor)
    acl_minimum = next((a["minimum_role"] for a in store.rag_category_acls(project_id) if a["category"] == category), "viewer")
    if ROLES.get(role, -1) < ROLES.get(acl_minimum, 0):
        raise HTTPException(403, f"Rôle « {acl_minimum} » requis pour la catégorie « {category} »")
    return role


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
def list_documents(request: Request, project: Path = Depends(project_dir)):
    current = actor_from_request(request)
    store.require_project_role(project.name, current)
    allowed = store.rag_categories_allowed(project.name, store.project_role(project.name, current))
    documents_dir = project / "rag" / "documents"
    documents_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    for path in sorted(documents_dir.glob("*/*.md")):
        if path.parent.name not in allowed:
            continue
        summaries.append(_summarize(path, path.parent.name))
    return summaries


@router.post("/documents", response_model=RagDocumentSummary)
def create_document(body: RagDocumentCreate, request: Request, project: Path = Depends(project_dir)):
    _require_category_role(project.name, actor_from_request(request), body.category, floor="operator")
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
async def upload_document(project_id: str, request: Request, file: UploadFile, category: str = Form("other")):
    project = project_dir(project_id)
    _validate_category(category)
    _require_category_role(project_id, actor_from_request(request), category, floor="operator")
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
def delete_document(category: str, filename: str, request: Request, project: Path = Depends(project_dir)):
    _require_category_role(project.name, actor_from_request(request), category, floor="operator")
    path = _safe_md_path(project, category, filename)
    if not path.exists():
        raise HTTPException(404, f"no such document: {category}/{filename}")
    path.unlink()
    job_id = _trigger_auto_reindex(project) if any((project / "rag" / "documents").glob("*/*.md")) else None
    return {"deleted": True, "reindex_job_id": job_id}


@router.post("/reindex", response_model=JobStatus)
def reindex(request: Request, project: Path = Depends(project_dir)):
    store.require_project_role(project.name, actor_from_request(request), "operator")
    if not any((project / "rag" / "documents").glob("*/*.md")):
        raise HTTPException(400, "no documents in rag/documents/ to index")
    job = registry.start_reindex(project)
    return JobStatus(job_id=job.job_id, kind="reindex", status=job.status, started_at=job.started_at, log_tail=[])


@router.post("/search", response_model=list[RagSearchResult])
def search(body: RagSearchRequest, request: Request, project: Path = Depends(project_dir)):
    current = actor_from_request(request)
    store.require_project_role(project.name, current)
    allowed = store.rag_categories_allowed(project.name, store.project_role(project.name, current))
    try:
        chunks = retrieve(body.query, project, top_k=body.top_k)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    # F07 "recherche vectorielle filtrée par... droits de l'utilisateur" — filtered after
    # retrieval rather than pushed into the vector query itself (rag/retriever.py has no
    # notion of ACLs), so a heavily-restricted actor can get fewer than top_k results.
    return [RagSearchResult(chunk_id=c.chunk_id, doc_id=c.doc_id, category=c.category, text=c.text, score=c.score)
            for c in chunks if c.category in allowed]


@router.get("/eval-queries", response_model=list[RagEvalQuery])
def list_eval_queries(request: Request, project: Path = Depends(project_dir)):
    store.require_project_role(project.name, actor_from_request(request))
    return rag_evaluation.load_eval_queries(project)


@router.post("/eval-queries", response_model=RagEvalQuery, status_code=201)
def create_eval_query(body: RagEvalQuery, request: Request, project: Path = Depends(project_dir)):
    store.require_project_role(project.name, actor_from_request(request), "operator")
    queries = rag_evaluation.load_eval_queries(project)
    if any(q["id"] == body.id for q in queries):
        raise HTTPException(409, f"la requête d'évaluation {body.id} existe déjà")
    item = body.model_dump()
    rag_evaluation.save_eval_queries(project, [*queries, item])
    return item


@router.delete("/eval-queries/{query_id}")
def delete_eval_query(query_id: str, request: Request, project: Path = Depends(project_dir)):
    store.require_project_role(project.name, actor_from_request(request), "operator")
    queries = rag_evaluation.load_eval_queries(project)
    kept = [q for q in queries if q["id"] != query_id]
    if len(kept) == len(queries):
        raise HTTPException(404, f"requête d'évaluation inconnue : {query_id}")
    rag_evaluation.save_eval_queries(project, kept)
    return {"deleted": True}


@router.post("/evaluate", response_model=RagEvalResult)
def evaluate_retrieval(request: Request, top_k: int = 5, project: Path = Depends(project_dir)):
    """Recall@K + MRR against rag/eval_queries.jsonl, with the full retrieved
    chunk list per query for audit (CLAUDE.md §12) — retrieval only, see
    RagEvalResult docstring for what this doesn't cover."""
    store.require_project_role(project.name, actor_from_request(request))
    if not rag_evaluation.load_eval_queries(project):
        raise HTTPException(400, "aucune requête d'évaluation — ajoute-en via POST .../rag/eval-queries")
    try:
        return rag_evaluation.evaluate(project, top_k=top_k)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@router.get("/acls", response_model=list[RagCategoryAcl])
def list_rag_acls(request: Request, project: Path = Depends(project_dir)):
    store.require_project_role(project.name, actor_from_request(request))
    return store.rag_category_acls(project.name)


@router.put("/acls", response_model=RagCategoryAcl)
def update_rag_acl(body: RagCategoryAclUpdate, request: Request, project: Path = Depends(project_dir)):
    current = actor_from_request(request)
    store.require_project_role(project.name, current, "admin")
    result = store.set_rag_category_acl(project.name, body.category, body.minimum_role)
    store.audit(current.id, "rag.acl.updated", "rag_category_acl", body.category, project.name,
                {"category": body.category, "minimum_role": body.minimum_role})
    return result
