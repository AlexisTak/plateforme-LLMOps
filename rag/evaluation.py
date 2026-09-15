"""Retrieval quality — Recall@K and MRR against a labeled set of queries with
known relevant documents (project/rag/eval_queries.jsonl), auditable per
query: question -> retrieved chunks -> scores. Retrieval only, no LLM call —
says nothing about whether an eventual answer is grounded in these chunks
(see docs/RUNTIME_FIXES.md, "Le benchmark actuel ne mesure pas l'ancrage
dans le RAG" — this narrows that gap for the retriever, not the generator).
"""

from __future__ import annotations

import json
from pathlib import Path

from rag.retriever import retrieve

EVAL_QUERIES_RELATIVE_PATH = "rag/eval_queries.jsonl"


def _eval_queries_path(project: Path) -> Path:
    return project / EVAL_QUERIES_RELATIVE_PATH


def load_eval_queries(project: Path) -> list[dict]:
    path = _eval_queries_path(project)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def save_eval_queries(project: Path, queries: list[dict]) -> None:
    path = _eval_queries_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(json.dumps(q, ensure_ascii=False) + "\n" for q in queries)
    path.write_text(content, encoding="utf-8")


def evaluate(project: Path, top_k: int = 5) -> dict:
    queries = load_eval_queries(project)
    per_query = []
    hits = 0
    reciprocal_ranks = []

    for item in queries:
        relevant = set(item["relevant_doc_ids"])
        chunks = retrieve(item["query"], project, top_k=top_k)
        rank = next((i + 1 for i, chunk in enumerate(chunks) if chunk.doc_id in relevant), None)
        hit = rank is not None
        hits += int(hit)
        reciprocal_ranks.append(1 / rank if hit else 0.0)
        per_query.append({
            "id": item["id"],
            "query": item["query"],
            "relevant_doc_ids": sorted(relevant),
            "hit": hit,
            "rank": rank,
            "chunks": [
                {"chunk_id": c.chunk_id, "doc_id": c.doc_id, "category": c.category, "score": c.score, "text": c.text}
                for c in chunks
            ],
        })

    n = len(queries)
    return {
        "top_k": top_k,
        "n_queries": n,
        "recall_at_k": round(hits / n, 3) if n else None,
        "mrr": round(sum(reciprocal_ranks) / n, 3) if n else None,
        "queries": per_query,
    }
