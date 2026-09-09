"""Build the persistent vector index from a project's rag/documents/ (mission
rule 27). Each project has its own index directory — nothing shared.

Choice, from rag/compare_embeddings.py (see rag/embedding_comparison.json):
  - embedding model: intfloat/multilingual-e5-small (91.7% top-1 vs 75-83% for
    paraphrase-multilingual-MiniLM-L12-v2, same 384-dim / same size class)
  - chunk size: 512 tokens, 50 token overlap (chunk size had ~no effect on this
    small corpus — documents are short enough that 512 and 768 produce the same
    6 chunks; 512 is the safer default as the corpus grows)

Usage:
    python -m rag.index --project-dir projects/biscuits-focus
"""

from __future__ import annotations

from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from rag.chunker import chunk_all_documents

COLLECTION_NAME = "docs"
EMBEDDING_MODEL = "intfloat/multilingual-e5-small"
CHUNK_MAX_TOKENS = 512
CHUNK_OVERLAP_TOKENS = 50
PASSAGE_PREFIX = "passage: "  # e5 convention


def build_index(project_dir: Path) -> tuple[int, int]:
    documents_dir = project_dir / "rag" / "documents"
    index_dir = project_dir / "rag" / "index"

    chunks = chunk_all_documents(documents_dir, max_tokens=CHUNK_MAX_TOKENS, overlap_tokens=CHUNK_OVERLAP_TOKENS)
    n_documents = len({c.doc_id for c in chunks})
    print(f"{len(chunks)} chunks from {documents_dir}")

    model = SentenceTransformer(EMBEDDING_MODEL)
    embeddings = model.encode([PASSAGE_PREFIX + c.text for c in chunks], normalize_embeddings=True, show_progress_bar=True) if chunks else []

    client = chromadb.PersistentClient(path=str(index_dir))
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.create_collection(COLLECTION_NAME, metadata={"embedding_model": EMBEDDING_MODEL})

    if chunks:
        collection.add(
            ids=[c.chunk_id for c in chunks],
            embeddings=[e.tolist() for e in embeddings],
            documents=[c.text for c in chunks],
            metadatas=[{"doc_id": c.doc_id, "category": c.category, "token_count": c.token_count} for c in chunks],
        )
    print(f"Index built at {index_dir} ({collection.count()} vectors)")
    return len(chunks), n_documents


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, required=True, help="e.g. projects/biscuits-focus")
    args = parser.parse_args()
    build_index(args.project_dir)
