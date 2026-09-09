"""Print dataset stats: counts, length distribution (chars + tokens), category
breakdown, duplicate count, vocabulary size. Used to sanity-check a dataset
before training and to pick max_seq_length (see training/configs/*.yaml).

Usage:
    python scripts/analyze_dataset.py "datasets/**/*.jsonl"
    python scripts/analyze_dataset.py "data/train/*.jsonl"
"""

from __future__ import annotations

import argparse
import glob
import json
import statistics
from collections import Counter
from pathlib import Path

from transformers import AutoTokenizer

MODEL_NAME = "unsloth/Llama-3.2-1B-Instruct"


def percentile(values: list[int], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    k = (len(values) - 1) * p
    f, c = int(k), min(int(k) + 1, len(values) - 1)
    return values[f] + (values[c] - values[f]) * (k - f)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("patterns", nargs="+")
    parser.add_argument("--skip-tokenizer", action="store_true", help="skip token-length stats (char stats only)")
    args = parser.parse_args()

    files: list[Path] = []
    for pattern in args.patterns:
        files.extend(Path(p) for p in glob.glob(pattern, recursive=True))
    files = sorted(set(files))

    examples = []
    category_counts: Counter = Counter()
    for path in files:
        cat = path.parent.name
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                examples.append((obj, cat))
                category_counts[cat] += 1

    print(f"Files: {len(files)}")
    print(f"Examples: {len(examples)}")
    print("\nBy category:")
    for cat, n in category_counts.most_common():
        print(f"  {cat}: {n}")

    char_lengths = []
    assistant_char_lengths = []
    seen_texts = Counter()
    vocab = set()
    for obj, _ in examples:
        full_text = " ".join(m["content"] for m in obj["messages"])
        char_lengths.append(len(full_text))
        vocab.update(full_text.lower().split())
        seen_texts[full_text] += 1
        for m in obj["messages"]:
            if m["role"] == "assistant":
                assistant_char_lengths.append(len(m["content"]))

    dupes = {t: c for t, c in seen_texts.items() if c > 1}

    print(f"\nChar length (full conversation): mean={statistics.mean(char_lengths):.0f}, "
          f"p50={percentile(char_lengths, 0.5):.0f}, p95={percentile(char_lengths, 0.95):.0f}, "
          f"p99={percentile(char_lengths, 0.99):.0f}, max={max(char_lengths)}")
    if assistant_char_lengths:
        print(f"Assistant response char length: mean={statistics.mean(assistant_char_lengths):.0f}, "
              f"p95={percentile(assistant_char_lengths, 0.95):.0f}, max={max(assistant_char_lengths)}")
    print(f"Vocabulary (whitespace tokens, lowercased): {len(vocab)} unique")
    print(f"Exact-duplicate conversations: {len(dupes)}")

    if not args.skip_tokenizer:
        print(f"\nTokenizing with {MODEL_NAME} (set --skip-tokenizer to skip)...")
        tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        token_lengths = []
        for obj, _ in examples:
            text = tokenizer.apply_chat_template(obj["messages"], tokenize=False)
            token_lengths.append(len(tokenizer(text)["input_ids"]))
        print(f"Token length: mean={statistics.mean(token_lengths):.0f}, "
              f"p50={percentile(token_lengths, 0.5):.0f}, p95={percentile(token_lengths, 0.95):.0f}, "
              f"p99={percentile(token_lengths, 0.99):.0f}, max={max(token_lengths)}")
        over_1024 = sum(1 for t in token_lengths if t > 1024)
        if over_1024:
            print(f"WARNING: {over_1024} example(s) exceed 1024 tokens (current max_seq_length in configs) — will be truncated.")


if __name__ == "__main__":
    main()
