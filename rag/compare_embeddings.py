"""Compare embedding models x chunk sizes on retrieval accuracy (mission rules 28-29).

Retrieval-only eval (top-1 accuracy against rag/eval_queries.jsonl), in-memory —
no vector store needed for comparison, that's a separate concern (rag/index.py).

Usage:
    python rag/compare_embeddings.py
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from rag.chunker import chunk_all_documents

ROOT = Path(__file__).resolve().parent.parent
EVAL_QUERIES_PATH = ROOT / "rag" / "eval_queries.jsonl"

CANDIDATES = [
    {
        "name": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "query_prefix": "",
        "passage_prefix": "",
    },
    {
        "name": "intfloat/multilingual-e5-small",
        # e5 models are trained with "query: "/"passage: " prefixes — required for
        # correct retrieval behavior per the model's documented usage convention.
        "query_prefix": "query: ",
        "passage_prefix": "passage: ",
    },
]

CHUNK_SIZES = [256, 512, 768]


def load_eval_queries() -> list[dict]:
    with EVAL_QUERIES_PATH.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def evaluate(model_name: str, query_prefix: str, passage_prefix: str, max_tokens: int) -> dict:
    chunks = chunk_all_documents(max_tokens=max_tokens, overlap_tokens=max(20, max_tokens // 10))
    queries = load_eval_queries()

    load_start = time.time()
    model = SentenceTransformer(model_name)
    load_time = time.time() - load_start

    passage_texts = [passage_prefix + c.text for c in chunks]
    embed_start = time.time()
    passage_embeddings = model.encode(passage_texts, normalize_embeddings=True, show_progress_bar=False)
    embed_time = time.time() - embed_start

    query_texts = [query_prefix + q["query"] for q in queries]
    query_embeddings = model.encode(query_texts, normalize_embeddings=True, show_progress_bar=False)

    sims = query_embeddings @ passage_embeddings.T
    top1_indices = sims.argmax(axis=1)

    correct = 0
    for i, q in enumerate(queries):
        retrieved_doc = chunks[top1_indices[i]].doc_id
        if retrieved_doc == q["expected_doc"]:
            correct += 1

    return {
        "model": model_name,
        "max_tokens": max_tokens,
        "n_chunks": len(chunks),
        "n_queries": len(queries),
        "top1_accuracy": round(correct / len(queries), 3),
        "model_load_seconds": round(load_time, 2),
        "embed_seconds_for_corpus": round(embed_time, 2),
        "embedding_dim": passage_embeddings.shape[1],
    }


def main() -> None:
    results = []
    for candidate in CANDIDATES:
        for max_tokens in CHUNK_SIZES:
            print(f"Evaluating {candidate['name']} @ max_tokens={max_tokens}...")
            result = evaluate(candidate["name"], candidate["query_prefix"], candidate["passage_prefix"], max_tokens)
            results.append(result)
            print(f"  top1_accuracy={result['top1_accuracy']} n_chunks={result['n_chunks']} dim={result['embedding_dim']}")

    print("\n=== Summary ===")
    header = f"{'model':<55} {'max_tok':>8} {'chunks':>7} {'acc':>6} {'dim':>5} {'load_s':>7} {'embed_s':>8}"
    print(header)
    print("-" * len(header))
    for r in results:
        print(f"{r['model']:<55} {r['max_tokens']:>8} {r['n_chunks']:>7} {r['top1_accuracy']:>6} {r['embedding_dim']:>5} {r['model_load_seconds']:>7} {r['embed_seconds_for_corpus']:>8}")

    output_path = ROOT / "rag" / "embedding_comparison.json"
    output_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nWritten to {output_path}")


if __name__ == "__main__":
    main()
