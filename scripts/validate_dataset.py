"""Validate JSONL conversation files against the Biscuits Focus dataset contract.

Usage:
    python scripts/validate_dataset.py datasets/**/*.jsonl
    python scripts/validate_dataset.py data/train/*.jsonl data/test/*.jsonl --check-leakage
"""

from __future__ import annotations

import argparse
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


def validate_example(obj: dict, file: str, line_no: int) -> list[Finding]:
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
            if len(content) > MAX_ASSISTANT_CHARS:
                findings.append(
                    Finding(file, line_no, "warning", f"assistant response too long ({len(content)} chars > {MAX_ASSISTANT_CHARS})")
                )
            stripped = content.strip()
            if stripped.startswith("{"):
                try:
                    json.loads(stripped)
                except json.JSONDecodeError as e:
                    findings.append(Finding(file, line_no, "error", f"assistant content looks like JSON but is invalid: {e}"))
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
    """Hash of the conversation content, for duplicate detection."""
    payload = json.dumps(obj.get("messages", []), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
