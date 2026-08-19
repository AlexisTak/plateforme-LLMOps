"""Dataset browsing/editing + validation/prepare endpoints, scoped to one project.

Reuses scripts/validate_dataset.py and scripts/prepare_dataset.py directly
(scripts/ is a plain importable package — see scripts/__init__.py) instead of
duplicating the validation rules or the split logic. Every path here lives
under the project's own directory (see api/paths.py) — datasets/RAG are not
shared between projects.

Route order matters here: FastAPI/Starlette matches routes by declaration
order, and "/{category}" matches any single path segment — including literal
ones like "validate" or "prepare". Static routes MUST be declared before the
"/{category}" catch-all routes, or e.g. POST .../dataset/validate gets routed
to add_example(category="validate") instead, and fails with a confusing 422
about a missing "file"/"messages" body (this happened once, see git history).
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from api.paths import project_dir
from api.schemas import (
    AddExampleRequest,
    CurrentDatasetVersion,
    DatasetCategorySummary,
    DatasetExample,
    DatasetStats,
    DeduplicateResult,
    Message,
    PrepareDatasetRequest,
    PrepareDatasetResult,
    UpdateExampleRequest,
    ValidationFinding,
    ValidationResult,
)
from scripts import prepare_dataset as prepare_mod
from scripts import validate_dataset as validate_mod

router = APIRouter(prefix="/api/projects/{project_id}/dataset", tags=["dataset"])


def _category_dir(project: Path, category: str) -> Path:
    path = project / "datasets" / category
    if not path.exists() or not path.is_dir():
        raise HTTPException(404, f"unknown category: {category}")
    return path


def _read_lines(path: Path) -> list[dict]:
    lines = []
    if not path.exists():
        return lines
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if raw:
                lines.append(json.loads(raw))
    return lines


def _write_lines(path: Path, lines: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for obj in lines:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


# --- Static routes first (see module docstring) -----------------------------


@router.get("/categories", response_model=list[DatasetCategorySummary])
def list_categories(project: Path = Depends(project_dir)):
    datasets_dir = project / "datasets"
    if not datasets_dir.exists():
        return []
    summaries = []
    for cat_dir in sorted(p for p in datasets_dir.iterdir() if p.is_dir()):
        files = sorted(p.name for p in cat_dir.glob("*.jsonl"))
        count = sum(len(_read_lines(cat_dir / f)) for f in files)
        summaries.append(DatasetCategorySummary(category=cat_dir.name, files=files, example_count=count))
    return summaries


@router.post("/validate", response_model=ValidationResult)
def validate_all(project: Path = Depends(project_dir)):
    files = sorted((project / "datasets").glob("*/*.jsonl"))
    all_findings: list[ValidationFinding] = []
    total_examples = 0
    seen_hashes: dict[str, list[str]] = {}

    for path in files:
        examples, load_findings = validate_mod.load_jsonl(path)
        for f in load_findings:
            all_findings.append(ValidationFinding(file=f.file, line=f.line, level=f.level, message=f.message))
        for obj, line_no in examples:
            total_examples += 1
            for f in validate_mod.validate_example(obj, str(path), line_no):
                all_findings.append(ValidationFinding(file=f.file, line=f.line, level=f.level, message=f.message))
            h = validate_mod.example_key(obj)
            seen_hashes.setdefault(h, []).append(f"{path}:{line_no}")

    for h, locations in seen_hashes.items():
        if len(locations) > 1:
            all_findings.append(ValidationFinding(file=locations[0], line=0, level="warning", message=f"duplicate also at: {', '.join(locations[1:])}"))

    errors = sum(1 for f in all_findings if f.level == "error")
    warnings = sum(1 for f in all_findings if f.level == "warning")
    return ValidationResult(total_examples=total_examples, total_files=len(files), errors=errors, warnings=warnings, findings=all_findings)


@router.post("/prepare", response_model=PrepareDatasetResult)
def prepare(body: PrepareDatasetRequest, project: Path = Depends(project_dir)):
    datasets_dir = project / "datasets"
    data_dir = project / "data"

    raw = prepare_mod.load_all(datasets_dir)
    cleaned = [(prepare_mod.clean(obj), cat) for obj, cat in raw]
    prepare_mod.write_jsonl(data_dir / "raw" / "all.jsonl", [obj for obj, _ in cleaned])
    prepare_mod.write_jsonl(data_dir / "cleaned" / "all.jsonl", [obj for obj, _ in cleaned])

    train, val, test = prepare_mod.stratified_split(cleaned, seed=body.seed)
    prepare_mod.write_jsonl(data_dir / "train" / "train.jsonl", train)
    prepare_mod.write_jsonl(data_dir / "validation" / "validation.jsonl", val)
    prepare_mod.write_jsonl(data_dir / "test" / "test.jsonl", test)
    (data_dir / "VERSION").write_text(body.version + "\n", encoding="utf-8")

    return PrepareDatasetResult(version=body.version, train=len(train), validation=len(val), test=len(test))


@router.post("/deduplicate", response_model=DeduplicateResult)
def deduplicate(project: Path = Depends(project_dir)):
    """Exact-duplicate removal across this project's datasets/*/*.jsonl, in
    place. Reuses validate_dataset.example_key (same hash used to flag dupes
    in /validate)."""
    total_before = 0
    total_after = 0
    removed_by_file: dict[str, int] = {}
    seen: set[str] = set()

    for path in sorted((project / "datasets").glob("*/*.jsonl")):
        lines = _read_lines(path)
        total_before += len(lines)
        kept = []
        removed_here = 0
        for obj in lines:
            h = validate_mod.example_key(obj)
            if h in seen:
                removed_here += 1
                continue
            seen.add(h)
            kept.append(obj)
        if removed_here:
            _write_lines(path, kept)
            removed_by_file[f"{path.parent.name}/{path.name}"] = removed_here
        total_after += len(kept)

    return DeduplicateResult(
        total_before=total_before,
        total_after=total_after,
        removed=total_before - total_after,
        removed_by_file=removed_by_file,
    )


@router.get("/meta/version", response_model=CurrentDatasetVersion)
def current_version(project: Path = Depends(project_dir)):
    """What scripts/prepare_dataset.py (or the 'Reconstruire' button) last wrote
    to data/VERSION + data/{train,validation,test} in this project — the
    dataset version actually on disk right now, as opposed to what any given
    experiment used historically."""
    data_dir = project / "data"
    version_path = data_dir / "VERSION"
    version = version_path.read_text(encoding="utf-8").strip() if version_path.exists() else None

    def count_split(name: str) -> int:
        split_dir = data_dir / name
        if not split_dir.exists():
            return 0
        return sum(len(_read_lines(p)) for p in split_dir.glob("*.jsonl"))

    return CurrentDatasetVersion(
        version=version,
        train=count_split("train"),
        validation=count_split("validation"),
        test=count_split("test"),
    )


@router.get("/meta/stats", response_model=DatasetStats)
def stats(project: Path = Depends(project_dir)):
    """Char-length + duplicate stats. No tokenizer load — kept fast for interactive UI use."""
    by_category: dict[str, int] = {}
    char_lengths: list[int] = []
    seen: dict[str, int] = {}

    for path in sorted((project / "datasets").glob("*/*.jsonl")):
        cat = path.parent.name
        for obj in _read_lines(path):
            by_category[cat] = by_category.get(cat, 0) + 1
            full_text = " ".join(m["content"] for m in obj["messages"])
            char_lengths.append(len(full_text))
            seen[full_text] = seen.get(full_text, 0) + 1

    total = sum(by_category.values())
    dupes = sum(1 for c in seen.values() if c > 1)

    def percentile(values: list[int], p: float) -> float:
        if not values:
            return 0.0
        values = sorted(values)
        k = (len(values) - 1) * p
        f, c = int(k), min(int(k) + 1, len(values) - 1)
        return values[f] + (values[c] - values[f]) * (k - f)

    return DatasetStats(
        total_examples=total,
        by_category=by_category,
        char_length_mean=round(statistics.mean(char_lengths), 1) if char_lengths else 0.0,
        char_length_p95=round(percentile(char_lengths, 0.95), 1),
        char_length_max=max(char_lengths) if char_lengths else 0,
        exact_duplicates=dupes,
    )


# --- Dynamic "/{category}..." routes last ------------------------------------


@router.get("/{category}", response_model=list[DatasetExample])
def list_examples(category: str, project: Path = Depends(project_dir)):
    cat_dir = _category_dir(project, category)
    examples = []
    for file_path in sorted(cat_dir.glob("*.jsonl")):
        for i, obj in enumerate(_read_lines(file_path)):
            examples.append(DatasetExample(file=file_path.name, index=i, messages=[Message(**m) for m in obj["messages"]]))
    return examples


@router.post("/{category}", response_model=DatasetExample)
def add_example(category: str, body: AddExampleRequest, project: Path = Depends(project_dir)):
    cat_dir = _category_dir(project, category)
    if not body.file.endswith(".jsonl") or "/" in body.file or "\\" in body.file:
        raise HTTPException(400, "file must be a bare *.jsonl filename")
    file_path = cat_dir / body.file
    lines = _read_lines(file_path)
    new_obj = {"messages": [m.model_dump() for m in body.messages]}
    lines.append(new_obj)
    _write_lines(file_path, lines)
    return DatasetExample(file=body.file, index=len(lines) - 1, messages=body.messages)


def _safe_jsonl_path(cat_dir: Path, file: str) -> Path:
    if not file.endswith(".jsonl") or "/" in file or "\\" in file:
        raise HTTPException(400, "file must be a bare *.jsonl filename")
    return cat_dir / file


@router.put("/{category}/{file}/{index}", response_model=DatasetExample)
def update_example(category: str, file: str, index: int, body: UpdateExampleRequest, project: Path = Depends(project_dir)):
    cat_dir = _category_dir(project, category)
    file_path = _safe_jsonl_path(cat_dir, file)
    lines = _read_lines(file_path)
    if index < 0 or index >= len(lines):
        raise HTTPException(404, f"no example at index {index} in {file}")
    lines[index] = {"messages": [m.model_dump() for m in body.messages]}
    _write_lines(file_path, lines)
    return DatasetExample(file=file, index=index, messages=body.messages)


@router.delete("/{category}/{file}/{index}")
def delete_example(category: str, file: str, index: int, project: Path = Depends(project_dir)):
    cat_dir = _category_dir(project, category)
    file_path = _safe_jsonl_path(cat_dir, file)
    lines = _read_lines(file_path)
    if index < 0 or index >= len(lines):
        raise HTTPException(404, f"no example at index {index} in {file}")
    lines.pop(index)
    _write_lines(file_path, lines)
    return {"deleted": True}
