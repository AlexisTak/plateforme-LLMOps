"""Deduplicate JSONL conversation files.

Two modes:
  1. Default: exact-duplicate removal within the given file(s), writes a
     deduplicated copy (or overwrites with --in-place).
  2. --check-splits: semantic near-duplicate check ACROSS multiple files
     (e.g. train vs test) using sentence-transformers embeddings —
     catches paraphrase leakage, not just exact-string matches
     (mission rule 16 / docs/DATASET_GUIDELINES.md).

Usage:
    python scripts/deduplicate_dataset.py data/raw/all.jsonl --in-place
    python scripts/deduplicate_dataset.py data/train/*.jsonl data/test/*.jsonl --check-splits --threshold 0.92
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    examples = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))
    return examples


def write_jsonl(path: Path, examples: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for obj in examples:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def conversation_text(obj: dict) -> str:
    return "\n".join(f"{m['role']}: {m['content']}" for m in obj["messages"])


def exact_dedupe(path: Path, in_place: bool) -> None:
    examples = load_jsonl(path)
    seen = set()
    kept = []
    for obj in examples:
        h = hashlib.sha256(conversation_text(obj).encode("utf-8")).hexdigest()
        if h in seen:
            continue
        seen.add(h)
        kept.append(obj)

    removed = len(examples) - len(kept)
    out_path = path if in_place else path.with_stem(path.stem + ".deduped")
    write_jsonl(out_path, kept)
    print(f"{path}: {len(examples)} -> {len(kept)} ({removed} exact duplicate(s) removed) -> {out_path}")


def check_splits(files: list[Path], threshold: float) -> int:
    from sentence_transformers import SentenceTransformer, util

    model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

    all_examples = []  # (text, file, line_index)
    for path in files:
        for i, obj in enumerate(load_jsonl(path)):
            all_examples.append((conversation_text(obj), str(path), i))

    texts = [t for t, _, _ in all_examples]
    embeddings = model.encode(texts, convert_to_tensor=True, show_progress_bar=True, normalize_embeddings=True)
    sims = util.cos_sim(embeddings, embeddings)

    leaks = 0
    n = len(all_examples)
    for i in range(n):
        for j in range(i + 1, n):
            file_i, file_j = all_examples[i][1], all_examples[j][1]
            if file_i == file_j:
                continue  # only cross-file leakage matters here
            score = sims[i][j].item()
            if score >= threshold:
                leaks += 1
                print(f"POSSIBLE LEAK ({score:.3f}): {file_i}#{all_examples[i][2]} ~= {file_j}#{all_examples[j][2]}")

    print(f"\n{leaks} possible cross-file near-duplicate pair(s) at threshold {threshold}.")
    return leaks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("patterns", nargs="+")
    parser.add_argument("--in-place", action="store_true")
    parser.add_argument("--check-splits", action="store_true")
    parser.add_argument("--threshold", type=float, default=0.92)
    args = parser.parse_args()

    files: list[Path] = []
    for pattern in args.patterns:
        files.extend(Path(p) for p in glob.glob(pattern, recursive=True))
    files = sorted(set(files))

    if not files:
        print("No files matched.")
        return 2

    if args.check_splits:
        leaks = check_splits(files, args.threshold)
        return 1 if leaks else 0

    for path in files:
        exact_dedupe(path, args.in_place)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
