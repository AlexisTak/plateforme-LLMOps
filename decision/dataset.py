"""Decision dataset storage/validation — one JSONL file per split under
projects/<id>/decision/dataset/{train,validation,test}.jsonl, each line
{"input": str, "decision": str}. Deliberately separate from api/routes/dataset.py
(chat-turn DatasetExample) since the shapes don't overlap — see mission §4."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from api.schemas import (
    DecisionClassStat,
    DecisionDatasetStats,
    DecisionExample,
    DecisionSchema,
    DecisionValidationFinding,
    DecisionValidationResult,
)
from api.storage import atomic_write_text

SPLITS = ("train", "validation", "test")


def dataset_dir(project_dir: Path) -> Path:
    return project_dir / "decision" / "dataset"


def split_path(project_dir: Path, split: str) -> Path:
    return dataset_dir(project_dir) / f"{split}.jsonl"


def _stable_id(file: str, index: int, input_text: str, decision: str) -> str:
    digest = hashlib.sha256(f"{file}:{input_text}:{decision}".encode()).hexdigest()[:12]
    return f"{file[:-len('.jsonl')]}-{index}-{digest}"


def read_split(project_dir: Path, split: str) -> list[DecisionExample]:
    path = split_path(project_dir, split)
    if not path.exists():
        return []
    examples = []
    with path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            examples.append(DecisionExample(
                id=row.get("id") or _stable_id(f"{split}.jsonl", index, row["input"], row["decision"]),
                file=f"{split}.jsonl", index=index, input=row["input"], decision=row["decision"],
            ))
    return examples


def read_all(project_dir: Path) -> dict[str, list[DecisionExample]]:
    return {split: read_split(project_dir, split) for split in SPLITS}


def append_example(project_dir: Path, split: str, input_text: str, decision: str) -> DecisionExample:
    path = split_path(project_dir, split)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = read_split(project_dir, split)
    index = len(existing)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"input": input_text, "decision": decision}, ensure_ascii=False) + "\n")
    return DecisionExample(id=_stable_id(f"{split}.jsonl", index, input_text, decision), file=f"{split}.jsonl", index=index, input=input_text, decision=decision)


def update_example(project_dir: Path, split: str, index: int, input_text: str, decision: str) -> DecisionExample:
    examples = read_split(project_dir, split)
    if index < 0 or index >= len(examples):
        raise ValueError(f"index {index} hors limites pour {split}")
    rows = [{"input": e.input, "decision": e.decision} for e in examples]
    rows[index] = {"input": input_text, "decision": decision}
    atomic_write_text(split_path(project_dir, split), "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    return DecisionExample(id=_stable_id(f"{split}.jsonl", index, input_text, decision), file=f"{split}.jsonl", index=index, input=input_text, decision=decision)


def delete_example(project_dir: Path, split: str, index: int) -> None:
    examples = read_split(project_dir, split)
    if index < 0 or index >= len(examples):
        raise ValueError(f"index {index} hors limites pour {split}")
    rows = [{"input": e.input, "decision": e.decision} for i, e in enumerate(examples) if i != index]
    atomic_write_text(split_path(project_dir, split), "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def validate(project_dir: Path, schema: DecisionSchema) -> DecisionValidationResult:
    """Checks (mission §4): allowed decision, missing fields, duplicates."""
    allowed = set(schema.decisions)
    findings: list[DecisionValidationFinding] = []
    seen: dict[str, tuple[str, int]] = {}
    total = 0
    for split in SPLITS:
        for example in read_split(project_dir, split):
            total += 1
            if not example.input.strip():
                findings.append(DecisionValidationFinding(file=example.file, line=example.index + 1, level="error", message="input vide"))
            if not example.decision.strip():
                findings.append(DecisionValidationFinding(file=example.file, line=example.index + 1, level="error", message="decision manquante"))
            elif example.decision not in allowed:
                findings.append(DecisionValidationFinding(
                    file=example.file, line=example.index + 1, level="error",
                    message=f"decision '{example.decision}' hors du schema autorise ({sorted(allowed)})",
                ))
            key = example.input.strip().lower()
            if key in seen:
                other_file, other_line = seen[key]
                findings.append(DecisionValidationFinding(
                    file=example.file, line=example.index + 1, level="warning",
                    message=f"doublon de l'input a {other_file}:{other_line}",
                ))
            else:
                seen[key] = (example.file, example.index + 1)
    errors = sum(1 for f in findings if f.level == "error")
    warnings = sum(1 for f in findings if f.level == "warning")
    return DecisionValidationResult(total_examples=total, errors=errors, warnings=warnings, findings=findings)


def stats(project_dir: Path) -> DecisionDatasetStats:
    by_split: dict[str, int] = {}
    counts: dict[str, int] = {}
    for split in SPLITS:
        examples = read_split(project_dir, split)
        by_split[split] = len(examples)
        for example in examples:
            counts[example.decision] = counts.get(example.decision, 0) + 1
    classes = [DecisionClassStat(decision=d, count=c) for d, c in sorted(counts.items(), key=lambda kv: -kv[1])]
    total = sum(by_split.values())
    if classes:
        smallest, largest = min(c.count for c in classes), max(c.count for c in classes)
        balance_ratio = smallest / largest if largest else None
    else:
        smallest = largest = 0
        balance_ratio = None
    return DecisionDatasetStats(total_examples=total, by_split=by_split, classes=classes, smallest_class=smallest, largest_class=largest, balance_ratio=balance_ratio)
