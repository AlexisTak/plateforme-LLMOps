"""Shared RAG constants without importing embedding or vector-store runtimes."""

COLLECTION_NAME = "docs"
EMBEDDING_MODEL = "intfloat/multilingual-e5-small"
CHUNK_MAX_TOKENS = 512
CHUNK_OVERLAP_TOKENS = 50
PASSAGE_PREFIX = "passage: "  # e5 convention
QUERY_PREFIX = "query: "  # e5 convention
