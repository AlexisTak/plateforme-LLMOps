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

import hashlib
import json
import os
import re
import statistics
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

from api.enterprise import actor_from_request
from api.paths import project_dir
from api.schemas import (
    AddExampleRequest,
    CurrentDatasetVersion,
    DatasetCategorySummary,
    DatasetExample,
    DatasetStats,
    DatasetVersionDiff,
    DatasetVersionManifest,
    DeduplicateResult,
    DuplicateExample,
    Message,
    NearDuplicatePair,
    PrepareDatasetRequest,
    PrepareDatasetResult,
    SplitLeak,
    UpdateExampleRequest,
    ValidationFinding,
    ValidationResult,
)
from scripts import dataset_versions
from scripts import prepare_dataset as prepare_mod
from scripts import validate_dataset as validate_mod

router = APIRouter(prefix="/api/projects/{project_id}/dataset", tags=["dataset"])


def _stable_id(obj: dict) -> str:
    """Deterministic id for examples that never got one backfilled via the
    dataset browsing UI (see _read_lines) — same cleaned content always
    yields the same id, so re-running prepare() without edits produces a
    stable diff instead of spurious add/remove churn."""
    canonical = json.dumps(obj.get("messages", []), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


# Categories are dynamic directory names under datasets/ (no fixed enum, see /categories),
# but they're still joined onto a filesystem path and used for read/write/delete below — must
# never contain "/", "..", or other path-traversal characters.
_SAFE_CATEGORY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _category_dir(project: Path, category: str) -> Path:
    if not _SAFE_CATEGORY.match(category):
        raise HTTPException(404, f"unknown category: {category}")
    datasets_dir = (project / "datasets").resolve()
    path = (datasets_dir / category).resolve()
    if datasets_dir not in path.parents or not path.exists() or not path.is_dir():
        raise HTTPException(404, f"unknown category: {category}")
    return path


def _read_lines(path: Path, *, skip_malformed: bool = False) -> list[dict]:
    """Read a JSONL file. Backfills a stable "id" on any object missing one
    and persists that backfill immediately — everything downstream (edit,
    delete, dedup) addresses examples by id, never by position, since the
    list order shifts under concurrent edits (see module docstring history).

    With skip_malformed=True, lines that fail to parse or lack the expected
    shape are dropped instead of raising, so one bad row doesn't 500 the
    whole dashboard — /validate is the place that reports those problems.
    """
    if not path.exists():
        return []
    lines = []
    backfilled = False
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                if skip_malformed:
                    continue
                raise
            if skip_malformed and (not isinstance(obj, dict) or not isinstance(obj.get("messages"), list)):
                continue
            if isinstance(obj, dict) and not obj.get("id"):
                obj["id"] = uuid.uuid4().hex
                backfilled = True
            lines.append(obj)
    if backfilled:
        _write_lines(path, lines)
    return lines


def _write_lines(path: Path, lines: list[dict]) -> None:
    """Atomic write: build the new content in a sibling .tmp file, fsync it,
    then os.replace() over the target. os.replace is atomic on both POSIX
    and NTFS, so a crash mid-write leaves either the old file or the new
    one intact — never a truncated/corrupt JSONL."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    with tmp.open("w", encoding="utf-8") as f:
        for obj in lines:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


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
    """Format validation, plus two informative-only signals that don't block
    anything here (no auto-removal): near-duplicate pairs within datasets/,
    and exact/normalized overlap between data/train and data/{validation,test}
    (i.e. train/test leakage from a prior `prepare`). Both just get reported
    in the response — the user decides what to do with them."""
    files = sorted((project / "datasets").glob("*/*.jsonl"))
    all_findings: list[ValidationFinding] = []
    total_examples = 0
    seen_hashes: dict[str, list[str]] = {}
    all_examples: list[tuple[dict, str, int]] = []
    meta_path = project / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    max_assistant_chars = int(meta.get("max_assistant_chars", 1500 if "project_type" not in meta else 8000))

    for path in files:
        examples, load_findings = validate_mod.load_jsonl(path)
        for f in load_findings:
            all_findings.append(ValidationFinding(file=f.file, line=f.line, level=f.level, message=f.message))
        for obj, line_no in examples:
            total_examples += 1
            for f in validate_mod.validate_example(
                obj,
                str(path),
                line_no,
                max_assistant_chars=max_assistant_chars,
            ):
                all_findings.append(ValidationFinding(file=f.file, line=f.line, level=f.level, message=f.message))
            h = validate_mod.example_key(obj)
            seen_hashes.setdefault(h, []).append(f"{path}:{line_no}")
            all_examples.append((obj, str(path), line_no))

    for locations in seen_hashes.values():
        if len(locations) > 1:
            all_findings.append(ValidationFinding(file=locations[0], line=0, level="warning", message=f"duplicate also at: {', '.join(locations[1:])}"))

    near_dup_pairs, near_dup_skipped = validate_mod.find_near_duplicates(all_examples)
    near_duplicates = [
        NearDuplicatePair(file_a=fa, line_a=la, file_b=fb, line_b=lb, similarity=sim) for fa, la, fb, lb, sim in near_dup_pairs
    ]

    split_leaks: list[SplitLeak] = []
    train_path = project / "data" / "train" / "train.jsonl"
    if train_path.exists():
        train_examples = [(obj, str(train_path), i + 1) for i, obj in enumerate(_read_lines(train_path, skip_malformed=True))]
        for split_name in ("validation", "test"):
            split_dir = project / "data" / split_name
            for split_path in sorted(split_dir.glob("*.jsonl")) if split_dir.exists() else []:
                split_examples = [(obj, str(split_path), i + 1) for i, obj in enumerate(_read_lines(split_path, skip_malformed=True))]
                for train_ref, split_file, split_ref in validate_mod.find_split_leakage(train_examples, split_examples):
                    split_leaks.append(SplitLeak(train_ref=train_ref, split_file=split_file, split_ref=split_ref))

    errors = sum(1 for f in all_findings if f.level == "error")
    warnings = sum(1 for f in all_findings if f.level == "warning")
    return ValidationResult(
        total_examples=total_examples,
        total_files=len(files),
        errors=errors,
        warnings=warnings,
        findings=all_findings,
        near_duplicates=near_duplicates,
        near_duplicate_scan_skipped=near_dup_skipped,
        split_leaks=split_leaks,
    )


@router.post("/prepare", response_model=PrepareDatasetResult)
def prepare(body: PrepareDatasetRequest, request: Request, project: Path = Depends(project_dir)):
    datasets_dir = project / "datasets"
    data_dir = project / "data"

    raw = prepare_mod.load_all(datasets_dir)
    cleaned = [(prepare_mod.clean(obj), cat) for obj, cat in raw]
    for obj, _cat in cleaned:
        if not obj.get("id"):
            obj["id"] = _stable_id(obj)
    prepare_mod.write_jsonl(data_dir / "raw" / "all.jsonl", [obj for obj, _ in cleaned])
    prepare_mod.write_jsonl(data_dir / "cleaned" / "all.jsonl", [obj for obj, _ in cleaned])

    train, val, test = prepare_mod.stratified_split(cleaned, seed=body.seed)
    prepare_mod.write_jsonl(data_dir / "train" / "train.jsonl", train)
    prepare_mod.write_jsonl(data_dir / "validation" / "validation.jsonl", val)
    prepare_mod.write_jsonl(data_dir / "test" / "test.jsonl", test)
    (data_dir / "VERSION").write_text(body.version + "\n", encoding="utf-8")

    actor = actor_from_request(request)
    try:
        manifest = dataset_versions.snapshot(project, body.version, body.seed, actor.email)
    except dataset_versions.VersionConflictError as exc:
        raise HTTPException(409, str(exc))
    except dataset_versions.InvalidVersionError as exc:
        raise HTTPException(400, str(exc))

    return PrepareDatasetResult(version=body.version, train=len(train), validation=len(val), test=len(test), sha256=manifest["sha256"])


@router.get("/versions", response_model=list[DatasetVersionManifest])
def list_dataset_versions(project: Path = Depends(project_dir)):
    return dataset_versions.list_versions(project)


@router.get("/versions/{version}", response_model=DatasetVersionManifest)
def get_dataset_version(version: str, project: Path = Depends(project_dir)):
    try:
        manifest = dataset_versions.get_version(project, version)
    except dataset_versions.InvalidVersionError as exc:
        raise HTTPException(400, str(exc))
    if manifest is None:
        raise HTTPException(404, f"version inconnue: {version}")
    return manifest


@router.get("/versions/{from_version}/diff/{to_version}", response_model=DatasetVersionDiff)
def diff_dataset_versions(from_version: str, to_version: str, project: Path = Depends(project_dir)):
    try:
        return dataset_versions.diff(project, from_version, to_version)
    except dataset_versions.InvalidVersionError as exc:
        raise HTTPException(400, str(exc))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@router.post("/deduplicate", response_model=DeduplicateResult)
def deduplicate(project: Path = Depends(project_dir), dry_run: bool = True):
    """Exact-duplicate removal across this project's datasets/*/*.jsonl.

    Defaults to dry_run=True: reports what *would* be removed without
    touching any file. Pass ?dry_run=false to actually apply it — mirrors
    the confirm() the UI already requires for deleting a single example."""
    total_before = 0
    total_after = 0
    removed_by_file: dict[str, int] = {}
    duplicates: list[DuplicateExample] = []
    seen: set[str] = set()

    for path in sorted((project / "datasets").glob("*/*.jsonl")):
        lines = _read_lines(path)
        total_before += len(lines)
        kept = []
        removed_here = 0
        for line_no, obj in enumerate(lines, start=1):
            h = validate_mod.example_key(obj)
            if h in seen:
                removed_here += 1
                duplicates.append(DuplicateExample(file=f"{path.parent.name}/{path.name}", line=line_no))
                continue
            seen.add(h)
            kept.append(obj)
        if removed_here:
            if not dry_run:
                _write_lines(path, kept)
            removed_by_file[f"{path.parent.name}/{path.name}"] = removed_here
        total_after += len(kept)

    return DeduplicateResult(
        dry_run=dry_run,
        total_before=total_before,
        total_after=total_after if not dry_run else total_before,
        removed=total_before - total_after if not dry_run else 0,
        removed_by_file=removed_by_file if not dry_run else {},
        duplicates=duplicates if dry_run else [],
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
        for obj in _read_lines(path, skip_malformed=True):
            by_category[cat] = by_category.get(cat, 0) + 1
            full_text = " ".join(m.get("content", "") for m in obj.get("messages", []) if isinstance(m, dict))
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
        for i, obj in enumerate(_read_lines(file_path, skip_malformed=True)):
            examples.append(DatasetExample(id=obj["id"], file=file_path.name, index=i, messages=[Message(**m) for m in obj["messages"]]))
    return examples


@router.post("/{category}", response_model=DatasetExample)
def add_example(category: str, body: AddExampleRequest, project: Path = Depends(project_dir)):
    cat_dir = _category_dir(project, category)
    if not body.file.endswith(".jsonl") or "/" in body.file or "\\" in body.file:
        raise HTTPException(400, "file must be a bare *.jsonl filename")
    file_path = cat_dir / body.file
    lines = _read_lines(file_path)
    new_id = uuid.uuid4().hex
    new_obj = {"id": new_id, "messages": [m.model_dump() for m in body.messages]}
    lines.append(new_obj)
    _write_lines(file_path, lines)
    return DatasetExample(id=new_id, file=body.file, index=len(lines) - 1, messages=body.messages)


def _find_by_id(cat_dir: Path, example_id: str) -> tuple[Path, list[dict], int]:
    """Locate an example by its stable id across every *.jsonl file in the
    category — never by position, since position shifts whenever another
    edit/delete/dedup happens between the list load and this call."""
    for file_path in sorted(cat_dir.glob("*.jsonl")):
        lines = _read_lines(file_path, skip_malformed=True)
        for i, obj in enumerate(lines):
            if obj.get("id") == example_id:
                return file_path, lines, i
    raise HTTPException(404, f"no example with id {example_id!r}")


@router.put("/{category}/{example_id}", response_model=DatasetExample)
def update_example(category: str, example_id: str, body: UpdateExampleRequest, project: Path = Depends(project_dir)):
    cat_dir = _category_dir(project, category)
    file_path, lines, index = _find_by_id(cat_dir, example_id)
    lines[index] = {"id": example_id, "messages": [m.model_dump() for m in body.messages]}
    _write_lines(file_path, lines)
    return DatasetExample(id=example_id, file=file_path.name, index=index, messages=body.messages)


@router.delete("/{category}/{example_id}")
def delete_example(category: str, example_id: str, project: Path = Depends(project_dir)):
    cat_dir = _category_dir(project, category)
    file_path, lines, index = _find_by_id(cat_dir, example_id)
    lines.pop(index)
    _write_lines(file_path, lines)
    return {"deleted": True}
