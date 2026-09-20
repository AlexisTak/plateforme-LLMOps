"""Merge hand-authored category files (datasets/) into the data/ pipeline:

    datasets/*/*.jsonl  -->  data/raw/all.jsonl  -->  data/cleaned/all.jsonl
                          --> data/train + data/validation + data/test (80/10/10)

Cleaning here is intentionally minimal (whitespace/empty-line normalization) —
substantive quality control is scripts/validate_dataset.py and human review
(see docs/DATASET_GUIDELINES.md), not silent auto-fixing.

Usage:
    python scripts/prepare_dataset.py --dataset-version dataset-v0.1
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Defaults kept for standalone CLI use (Jenkinsfile, manual runs) against a
# project passed via --project-dir; api/routes/dataset.py always passes an
# explicit datasets_dir instead of relying on these.
DATASETS_DIR = ROOT / "projects"
DATA_DIR = ROOT / "projects"


def category_of(path: Path, datasets_dir: Path) -> str:
    return path.relative_to(datasets_dir).parts[0]


def load_all(datasets_dir: Path) -> list[tuple[dict, str]]:
    examples = []
    for path in sorted(datasets_dir.glob("*/*.jsonl")):
        cat = category_of(path, datasets_dir)
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                examples.append((json.loads(line), cat))
    return examples


def clean(obj: dict) -> dict:
    for msg in obj["messages"]:
        msg["content"] = msg["content"].strip()
    return obj


def stratified_split(examples: list[tuple[dict, str]], seed: int, ratios=(0.8, 0.1, 0.1)):
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for obj, cat in examples:
        by_cat[cat].append(obj)

    rng = random.Random(seed)
    train, val, test = [], [], []
    for items in by_cat.values():
        rng.shuffle(items)
        n = len(items)
        n_train = max(1, int(n * ratios[0])) if n >= 3 else n
        n_val = max(1, int(n * ratios[1])) if n - n_train >= 2 else 0
        train.extend(items[:n_train])
        val.extend(items[n_train:n_train + n_val])
        test.extend(items[n_train + n_val:])
    return train, val, test


def write_jsonl(path: Path, examples: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for obj in examples:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, required=True, help="e.g. projects/biscuits-focus")
    parser.add_argument("--dataset-version", required=True, help="e.g. dataset-v0.1 — recorded in data/VERSION")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    datasets_dir = args.project_dir / "datasets"
    data_dir = args.project_dir / "data"

    raw = load_all(datasets_dir)
    print(f"Loaded {len(raw)} examples from {datasets_dir}")

    cleaned = [(clean(obj), cat) for obj, cat in raw]
    write_jsonl(data_dir / "raw" / "all.jsonl", [obj for obj, _ in cleaned])
    write_jsonl(data_dir / "cleaned" / "all.jsonl", [obj for obj, _ in cleaned])

    train, val, test = stratified_split(cleaned, seed=args.seed)
    write_jsonl(data_dir / "train" / "train.jsonl", train)
    write_jsonl(data_dir / "validation" / "validation.jsonl", val)
    write_jsonl(data_dir / "test" / "test.jsonl", test)

    (data_dir / "VERSION").write_text(args.dataset_version + "\n", encoding="utf-8")

    print(f"train={len(train)} validation={len(val)} test={len(test)}  (dataset version: {args.dataset_version})")
    print("Run scripts/validate_dataset.py and scripts/deduplicate_dataset.py --check-splits next.")


if __name__ == "__main__":
    main()
