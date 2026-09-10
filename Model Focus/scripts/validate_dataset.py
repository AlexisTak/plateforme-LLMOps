"""Validate JSONL conversation files against the Biscuits Focus dataset contract.

Usage:
    python scripts/validate_dataset.py datasets/**/*.jsonl
    python scripts/validate_dataset.py data/train/*.jsonl data/test/*.jsonl --check-leakage
"""

from __future__ import annotations

import argparse
import difflib
import glob
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

VALID_ROLES = {"system", "user", "assistant"}
MAX_ASSISTANT_CHARS = 1500
SENSITIVE_PATTERNS = [
    re.compile(r"\b\d{13,19}\b"),  # card-like numbers
    re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    re.compile(r"\bIBAN\b", re.IGNORECASE),
    re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b.{0,20}\b(né|naissance)\b", re.IGNORECASE),
]
MEDICAL_CLAIM_PATTERNS = [
    re.compile(r"\btu as (le|un) tdah\b", re.IGNORECASE),
    re.compile(r"\bje te (diagnostique|prescris)\b", re.IGNORECASE),
    re.compile(r"\bprends? (du|de la|le|la)\s+\w+(mg|mcg)\b", re.IGNORECASE),
]


class Finding:
    def __init__(self, file: str, line: int, level: str, message: str):
        self.file = file
        self.line = line
        self.level = level  # "error" | "warning"
        self.message = message

    def __str__(self) -> str:
        return f"[{self.level.upper()}] {self.file}:{self.line} — {self.message}"


def validate_example(
    obj: dict,
    file: str,
    line_no: int,
    *,
    medical_safety: bool = True,
    max_assistant_chars: int = MAX_ASSISTANT_CHARS,
) -> list[Finding]:
    findings: list[Finding] = []

    if not isinstance(obj, dict) or "messages" not in obj:
        findings.append(Finding(file, line_no, "error", "missing 'messages' key"))
        return findings

    messages = obj["messages"]
    if not isinstance(messages, list) or not messages:
        findings.append(Finding(file, line_no, "error", "'messages' must be a non-empty list"))
        return findings

    roles_seen = []
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict) or "role" not in msg or "content" not in msg:
            findings.append(Finding(file, line_no, "error", f"message[{i}] missing role/content"))
            continue
        role = msg["role"]
        content = msg["content"]
        roles_seen.append(role)
        if role not in VALID_ROLES:
            findings.append(Finding(file, line_no, "error", f"message[{i}] invalid role '{role}'"))
        if not isinstance(content, str) or not content.strip():
            findings.append(Finding(file, line_no, "error", f"message[{i}] empty/non-string content"))
            continue

        if role == "assistant":
            if len(content) > max_assistant_chars:
                findings.append(
                    Finding(file, line_no, "warning", f"assistant response too long ({len(content)} chars > {max_assistant_chars})")
                )
            stripped = content.strip()
            if stripped.startswith("{"):
                try:
                    json.loads(stripped)
                except json.JSONDecodeError as e:
                    findings.append(Finding(file, line_no, "error", f"assistant content looks like JSON but is invalid: {e}"))
            if medical_safety:
                for pat in MEDICAL_CLAIM_PATTERNS:
                    if pat.search(content):
                        findings.append(Finding(file, line_no, "error", f"possible medical diagnosis/prescription claim: matched {pat.pattern!r}"))

        for pat in SENSITIVE_PATTERNS:
            if pat.search(content):
                findings.append(Finding(file, line_no, "warning", f"possible sensitive data in {role} content: matched {pat.pattern!r}"))

    if "user" not in roles_seen:
        findings.append(Finding(file, line_no, "error", "no 'user' message present"))
    if "assistant" not in roles_seen:
        findings.append(Finding(file, line_no, "error", "no 'assistant' message present"))

    return findings


def example_key(obj: dict) -> str:
    """Hash of the conversation content, for exact-duplicate detection."""
    payload = json.dumps(obj.get("messages", []), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


_WS_PUNCT_RE = re.compile(r"[^\w]+", re.UNICODE)


def normalized_key(obj: dict) -> str:
    """Hash of the conversation content after case/whitespace/punctuation
    normalization — catches near-identical examples that differ only in
    formatting (a missing comma, extra space, capitalization)."""
    parts = []
    for m in obj.get("messages", []):
        content = m.get("content", "") if isinstance(m, dict) else ""
        parts.append(_WS_PUNCT_RE.sub(" ", content.lower()).strip())
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def full_text(obj: dict) -> str:
    return " ".join(m.get("content", "") for m in obj.get("messages", []) if isinstance(m, dict))


MAX_NEAR_DUP_PAIRS_SCANNED = 200_000  # O(n^2) guard: skip the scan rather than hang on a huge dataset


def find_near_duplicates(
    examples: list[tuple[dict, str, int]],
    threshold: float = 0.9,
) -> tuple[list[tuple[str, int, str, int, float]], bool]:
    """Near-duplicate scan using a fast TF-IDF candidate index, followed by
    the existing SequenceMatcher ratio for the final decision.

    Informative only — does not remove anything. Returns (pairs, skipped),
    where each pair is (file_a, line_a, file_b, line_b, similarity). The
    candidate threshold is deliberately permissive so formatting variants
    still reach the precise comparison without evaluating every possible pair.
    """
    n = len(examples)
    if n * (n - 1) // 2 > MAX_NEAR_DUP_PAIRS_SCANNED:
        return [], True

    if n < 2:
        return [], False

    texts = [full_text(obj) for obj, _, _ in examples]

    # Import locally: sklearn is only needed when a user explicitly launches
    # validation, so it must not slow down API startup or ordinary requests.
    from sklearn.feature_extraction.text import TfidfVectorizer

    vectors = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), lowercase=True).fit_transform(texts)
    similarities = vectors @ vectors.T
    rows, cols = similarities.nonzero()
    candidate_pairs = {
        (int(i), int(j))
        for i, j in zip(rows, cols)
        if i < j and similarities[i, j] >= 0.4
    }

    pairs: list[tuple[str, int, str, int, float]] = []
    matcher = difflib.SequenceMatcher(autojunk=False)
    for i, j in sorted(candidate_pairs):
        matcher.set_seq2(texts[i])
        if abs(len(texts[i]) - len(texts[j])) > max(len(texts[i]), len(texts[j])) * (1 - threshold) + 20:
            continue  # length gap alone rules out reaching `threshold`
        matcher.set_seq1(texts[j])
        ratio = matcher.quick_ratio()
        if ratio < threshold:
            continue
        ratio = matcher.ratio()
        if ratio >= threshold:
            _, file_a, line_a = examples[i]
            _, file_b, line_b = examples[j]
            pairs.append((file_a, line_a, file_b, line_b, round(ratio, 3)))
    return pairs, False


def find_split_leakage(
    train_examples: list[tuple[dict, str, int]],
    other_examples: list[tuple[dict, str, int]],
) -> list[tuple[str, str, str]]:
    """Exact + normalized overlap between train and another split (validation/test).
    Returns (train_ref, other_split_file, other_ref) triples."""
    train_exact = {example_key(obj): f"{file}:{line}" for obj, file, line in train_examples}
    train_norm = {normalized_key(obj): f"{file}:{line}" for obj, file, line in train_examples}

    leaks = []
    for obj, file, line in other_examples:
        ref = f"{file}:{line}"
        exact_hit = train_exact.get(example_key(obj))
        norm_hit = train_norm.get(normalized_key(obj))
        hit = exact_hit or norm_hit
        if hit:
            leaks.append((hit, file, ref))
    return leaks


def load_jsonl(path: Path) -> tuple[list[dict], list[Finding]]:
    examples = []
    findings = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, raw in enumerate(f, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as e:
                findings.append(Finding(str(path), line_no, "error", f"invalid JSON: {e}"))
                continue
            examples.append((obj, line_no))
    return examples, findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("patterns", nargs="+", help="glob pattern(s) to JSONL files")
    parser.add_argument("--check-leakage", action="store_true", help="warn on identical examples across different input files (e.g. train vs test)")
    args = parser.parse_args()

    files: list[Path] = []
    for pattern in args.patterns:
        files.extend(Path(p) for p in glob.glob(pattern, recursive=True))
    files = sorted(set(files))

    if not files:
        print("No files matched.", file=sys.stderr)
        return 2

    all_findings: list[Finding] = []
    seen_hashes: dict[str, list[str]] = defaultdict(list)  # hash -> [file:line, ...]
    total_examples = 0

    for path in files:
        examples, load_findings = load_jsonl(path)
        all_findings.extend(load_findings)
        for obj, line_no in examples:
            total_examples += 1
            all_findings.extend(validate_example(obj, str(path), line_no))
            h = example_key(obj)
            seen_hashes[h].append(f"{path}:{line_no}")

    for h, locations in seen_hashes.items():
        if len(locations) > 1:
            files_involved = {loc.split(":")[0] for loc in locations}
            level = "error" if (args.check_leakage and len(files_involved) > 1) else "warning"
            all_findings.append(Finding(locations[0], 0, level, f"duplicate example also found at: {', '.join(locations[1:])}"))

    errors = [f for f in all_findings if f.level == "error"]
    warnings = [f for f in all_findings if f.level == "warning"]

    for f in all_findings:
        print(f)

    print(f"\n{total_examples} examples across {len(files)} file(s). {len(errors)} error(s), {len(warnings)} warning(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
