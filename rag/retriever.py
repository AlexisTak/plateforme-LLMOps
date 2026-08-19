"""Query the persistent index built by rag/index.py, one per project."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from rag.index import COLLECTION_NAME, EMBEDDING_MODEL

QUERY_PREFIX = "query: "  # e5 convention

_model: SentenceTransformer | None = None
_collections: dict[str, object] = {}  # project_dir (str) -> Chroma collection handle


@dataclass
class RetrievedChunk:
    chunk_id: str
    doc_id: str
    category: str
    text: str
    score: float


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def _get_collection(project_dir: Path):
    key = str(project_dir)
    if key not in _collections:
        index_dir = project_dir / "rag" / "index"
        if not index_dir.exists():
            raise FileNotFoundError(f"no index at {index_dir} — run `python -m rag.index --project-dir {project_dir}` first")
        client = chromadb.PersistentClient(path=str(index_dir))
        _collections[key] = client.get_collection(COLLECTION_NAME)
    return _collections[key]


def reset_cache(project_dir: Path) -> None:
    """Drop the cached collection handle for this project — call after
    rebuilding its index (rag.index.build_index deletes and recreates the
    Chroma collection, so a stale cached handle from before the rebuild would
    point at nothing)."""
    _collections.pop(str(project_dir), None)


def retrieve(query: str, project_dir: Path, top_k: int = 3) -> list[RetrievedChunk]:
    model = _get_model()
    collection = _get_collection(project_dir)

    query_embedding = model.encode([QUERY_PREFIX + query], normalize_embeddings=True)[0].tolist()
    result = collection.query(query_embeddings=[query_embedding], n_results=top_k)

    chunks = []
    for i in range(len(result["ids"][0])):
        # chromadb returns squared L2 distance on normalized embeddings; convert to cosine similarity.
        distance = result["distances"][0][i]
        similarity = 1 - distance / 2
        chunks.append(
            RetrievedChunk(
                chunk_id=result["ids"][0][i],
                doc_id=result["metadatas"][0][i]["doc_id"],
                category=result["metadatas"][0][i]["category"],
                text=result["documents"][0][i],
                score=round(similarity, 4),
            )
        )
    return chunks
