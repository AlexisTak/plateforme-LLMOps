"""Immutable dataset version snapshots.

api/routes/dataset.py::prepare() calls snapshot() right after writing
data/{train,validation,test}/*.jsonl. Each snapshot is copied into
data/versions/<version>/ alongside a manifest carrying a SHA-256 fingerprint
of its contents. A version is immutable: snapshotting the same version
string again with different content is rejected — CLAUDE.md requires that an
old version never silently change. Re-snapshotting identical content is a
no-op (common case: rerunning the pipeline without dataset changes).

This lives next to the existing scripts/prepare_dataset.py rather than
replacing data/VERSION — that file remains the "what's on disk right now"
pointer consumed by training/evaluation; data/versions/ is the immutable
history alongside it.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

SPLIT_NAMES = ("train", "validation", "test")

# version becomes a directory name under data/versions/ — reject anything that
# could escape it ("..", "/", etc.), same pattern as the model registry's
# version field (api/routes/enterprise.py::VersionCreate).
_SAFE_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class VersionConflictError(ValueError):
    """Raised when re-snapshotting a version string with different content."""


class InvalidVersionError(ValueError):
    """Raised when a version string isn't a safe directory name."""


def _split_path(project: Path, split: str) -> Path:
    return project / "data" / split / f"{split}.jsonl"


def _read_examples(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _version_dir(project: Path, version: str) -> Path:
    if not _SAFE_VERSION.match(version):
        raise InvalidVersionError(f"version invalide: {version!r}")
    return project / "data" / "versions" / version


def _content_sha256(splits: dict[str, list[dict]]) -> str:
    canonical = json.dumps(splits, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def snapshot(project: Path, version: str, seed: int, author: str) -> dict:
    """Snapshot the splits currently on disk (data/{train,validation,test}/)
    into an immutable data/versions/<version>/ directory and return its manifest."""
    splits = {name: _read_examples(_split_path(project, name)) for name in SPLIT_NAMES}
    sha256 = _content_sha256(splits)
    version_dir = _version_dir(project, version)
    manifest_path = version_dir / "manifest.json"

    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing["sha256"] != sha256:
            raise VersionConflictError(
                f"la version {version!r} existe déjà avec un contenu différent — "
                "choisis un nouveau nom de version, une version ne change jamais silencieusement"
            )
        return existing

    version_dir.mkdir(parents=True, exist_ok=True)
    for name, examples in splits.items():
        lines = "\n".join(json.dumps(ex, ensure_ascii=False) for ex in examples)
        (version_dir / f"{name}.jsonl").write_text(lines + ("\n" if lines else ""), encoding="utf-8")

    manifest = {
        "version": version,
        "dataset": project.name,
        "author": author,
        "created_at": datetime.now(UTC).isoformat(),
        "splits": {name: len(examples) for name, examples in splits.items()},
        "example_count": sum(len(examples) for examples in splits.values()),
        "sha256": sha256,
        "seed": seed,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def list_versions(project: Path) -> list[dict]:
    versions_dir = project / "data" / "versions"
    if not versions_dir.exists():
        return []
    manifests = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(versions_dir.glob("*/manifest.json"))]
    manifests.sort(key=lambda m: m["created_at"])
    return manifests


def get_version(project: Path, version: str) -> dict | None:
    manifest_path = _version_dir(project, version) / "manifest.json"
    if not manifest_path.exists():
        return None
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _example_summary(example: dict) -> str:
    messages = example.get("messages", [])
    first_user = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")
    return first_user[:120]


def diff(project: Path, from_version: str, to_version: str) -> dict:
    """+ added / - removed / ~ modified examples between two immutable versions,
    matched by stable example id within each split."""
    if get_version(project, from_version) is None:
        raise FileNotFoundError(f"version inconnue: {from_version}")
    if get_version(project, to_version) is None:
        raise FileNotFoundError(f"version inconnue: {to_version}")

    added, removed, modified = [], [], []
    for split in SPLIT_NAMES:
        from_examples = {ex["id"]: ex for ex in _read_examples(_version_dir(project, from_version) / f"{split}.jsonl")}
        to_examples = {ex["id"]: ex for ex in _read_examples(_version_dir(project, to_version) / f"{split}.jsonl")}
        for example_id, example in to_examples.items():
            if example_id not in from_examples:
                added.append({"split": split, "id": example_id, "summary": _example_summary(example)})
            elif from_examples[example_id]["messages"] != example["messages"]:
                modified.append({"split": split, "id": example_id, "summary": _example_summary(example)})
        for example_id, example in from_examples.items():
            if example_id not in to_examples:
                removed.append({"split": split, "id": example_id, "summary": _example_summary(example)})

    return {"from_version": from_version, "to_version": to_version, "added": added, "removed": removed, "modified": modified}
