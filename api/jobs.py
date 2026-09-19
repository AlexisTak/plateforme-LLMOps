"""Background jobs with durable terminal history and process-tree cancellation.

Completed/failed/stopped jobs survive API restarts. Live processes are owned by
this API instance; terminal history is saved atomically under .jobs/.

Every job belongs to exactly one project — the subprocess is always launched
with --project-dir pointing at that project's own isolated workspace.
"""

from __future__ import annotations

import subprocess
import json
import os
import signal
import logging
import sys
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from api.storage import atomic_write_text

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable  # the venv interpreter running this API


@dataclass
class Job:
    job_id: str
    kind: str  # "training" | "evaluation" | "reindex" | "pipeline" | "sweep"
    project_dir: Path
    config_filename: str | None
    log_path: Path | None
    status: str = "running"  # running | completed | failed | stopped
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: str | None = None
    return_code: int | None = None
    process: subprocess.Popen | None = None
    stdout_lines: list[str] = field(default_factory=list)


class JobRegistry:
    def __init__(self, storage_dir: Path | None = None) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.RLock()
        # BISCUITS_JOBS_DIR mirrors BISCUITS_ENTERPRISE_DB: lets tests (tests/conftest.py)
        # and containers keep job history out of the source tree.
        self._storage_dir = storage_dir if storage_dir is not None else Path(os.getenv("BISCUITS_JOBS_DIR", ROOT / ".jobs"))
        self._threads: dict[str, threading.Thread] = {}
        self._reindex_pending: set[str] = set()  # project_dir keys with a reindex queued
        self._reindex_lock = threading.Lock()
        for path in self._storage_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                data["project_dir"] = Path(data["project_dir"])
                data["log_path"] = Path(data["log_path"]) if data["log_path"] else None
                self._jobs[data["job_id"]] = Job(**data)
            except (OSError, ValueError, KeyError, TypeError):
                logging.getLogger(__name__).exception("Cannot restore job history %s", path)

    def _persist(self, job: Job) -> None:
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        data = {name: getattr(job, name) for name in Job.__dataclass_fields__ if name != "process"}
        data["project_dir"] = str(job.project_dir)
        data["log_path"] = str(job.log_path) if job.log_path else None
        data["stdout_lines"] = job.stdout_lines[-200:]
        path = self._storage_dir / f"{job.job_id}.json"
        atomic_write_text(path, json.dumps(data, ensure_ascii=False))

    def start_training(self, project_dir: Path, config_filename: str, resume: bool = False) -> Job:
        config_path = project_dir / "training" / "configs" / config_filename
        if not config_path.exists():
            raise FileNotFoundError(f"config not found: {config_path}")

        job_id = str(uuid.uuid4())[:8]
        cmd = [PYTHON, str(ROOT / "training/scripts/train.py"), "--project-dir", str(project_dir), "--config", str(config_path)]
        if resume:
            cmd.append("--resume")

        job = Job(job_id=job_id, kind="training", project_dir=project_dir, config_filename=config_filename, log_path=None)
        self._launch(job, cmd)
        return job

    def start_pipeline(self, project_dir: Path, config_filename: str, dataset_version: str, resume: bool = False) -> Job:
        """Autonomous validate -> prepare -> train chain (scripts/run_pipeline.py),
        one subprocess, tracked as a single job — see that script's docstring."""
        config_path = project_dir / "training" / "configs" / config_filename
        if not config_path.exists():
            raise FileNotFoundError(f"config not found: {config_path}")

        job_id = str(uuid.uuid4())[:8]
        cmd = [
            PYTHON,
            str(ROOT / "scripts/run_pipeline.py"),
            "--project-dir",
            str(project_dir),
            "--config",
            str(config_path),
            "--dataset-version",
            dataset_version,
        ]
        if resume:
            cmd.append("--resume")

        job = Job(job_id=job_id, kind="pipeline", project_dir=project_dir, config_filename=config_filename, log_path=None)
        self._launch(job, cmd)
        return job

    def start_sweep(self, project_dir: Path, dataset_version: str, resume: bool = False) -> Job:
        """Runs scripts/run_sweep.py — trains r=8/16/32 sequentially, one job,
        continues past a single config's failure so you still get the others."""
        job_id = str(uuid.uuid4())[:8]
        cmd = [PYTHON, str(ROOT / "scripts/run_sweep.py"), "--project-dir", str(project_dir), "--dataset-version", dataset_version]
        if resume:
            cmd.append("--resume")
        job = Job(job_id=job_id, kind="sweep", project_dir=project_dir, config_filename=None, log_path=None)
        self._launch(job, cmd)
        return job

    def start_evaluation(self, project_dir: Path) -> Job:
        job_id = str(uuid.uuid4())[:8]
        cmd = [PYTHON, str(ROOT / "evaluation/run.py"), "--project-dir", str(project_dir)]
        job = Job(job_id=job_id, kind="evaluation", project_dir=project_dir, config_filename=None, log_path=project_dir / "evaluation/report.md")
        self._launch(job, cmd)
        return job

    def start_reindex(self, project_dir: Path) -> Job:
        """Runs `python -m rag.index` as a subprocess — kept out-of-process so a
        large corpus (many/large PDFs) can't block the API's event loop or hit
        an HTTP request timeout."""
        job_id = str(uuid.uuid4())[:8]
        cmd = [PYTHON, "-m", "rag.index", "--project-dir", str(project_dir)]
        job = Job(job_id=job_id, kind="reindex", project_dir=project_dir, config_filename=None, log_path=None)
        self._launch(job, cmd)
        return job

    def request_reindex(self, project_dir: Path) -> Job | None:
        """Auto-triggered after a RAG document add/delete. Debounced per project:
        if a reindex is already running for this project (e.g. two uploads in
        quick succession), this just flags that another pass is needed once the
        current one finishes, instead of starting a second `python -m rag.index`
        that would race the first one deleting/recreating that project's Chroma
        collection on disk."""
        key = str(project_dir)
        with self._reindex_lock:
            running = any(j.kind == "reindex" and j.status == "running" and str(j.project_dir) == key for j in self.list())
            if running:
                self._reindex_pending.add(key)
                return None
            self._reindex_pending.discard(key)
            return self.start_reindex(project_dir)

    def _maybe_start_pending_reindex(self, project_dir: Path) -> None:
        key = str(project_dir)
        with self._reindex_lock:
            if key not in self._reindex_pending:
                return
            self._reindex_pending.discard(key)
        self.request_reindex(project_dir)

    def _launch(self, job: Job, cmd: list[str]) -> None:
        if job.kind in ("training", "pipeline", "sweep"):
            cmd = [PYTHON, str(ROOT / "scripts/run_with_evaluation.py"),
                   "--project-dir", str(job.project_dir), "--", *cmd]
        process = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            start_new_session=os.name != "nt",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        job.process = process
        with self._lock:
            self._jobs[job.job_id] = job

        thread = threading.Thread(target=self._pump_output, args=(job,), daemon=True)
        self._threads[job.job_id] = thread
        thread.start()

    def _pump_output(self, job: Job) -> None:
        assert job.process is not None and job.process.stdout is not None
        for line in job.process.stdout:
            job.stdout_lines.append(line.rstrip("\n"))
            if len(job.stdout_lines) > 2000:
                job.stdout_lines = job.stdout_lines[-1000:]
        job.process.wait()
        with self._lock:
            job.return_code = job.process.returncode
            if job.status != "stopped":
                job.status = "completed" if job.return_code == 0 else "failed"
            job.finished_at = job.finished_at or datetime.now(timezone.utc).isoformat()
            self._persist(job)

        if job.kind == "reindex" and job.status == "completed":
            # rag.index ran in a subprocess and rebuilt this project's Chroma
            # collection on disk — this process's cached retriever handle would
            # otherwise keep pointing at the old (deleted) collection.
            from rag.retriever import reset_cache

            reset_cache(job.project_dir)
        if job.kind == "reindex" and job.status != "stopped":
            self._maybe_start_pending_reindex(job.project_dir)

    def shutdown(self) -> None:
        for job in self.list():
            if job.status == "running":
                self.stop(job.job_id)
        for thread in list(self._threads.values()):
            thread.join(timeout=5)

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list(self, project_dir: Path | None = None) -> list[Job]:
        with self._lock:
            jobs = list(self._jobs.values())
        if project_dir is not None:
            jobs = [j for j in jobs if str(j.project_dir) == str(project_dir)]
        return sorted(jobs, key=lambda j: j.started_at, reverse=True)

    def stop(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.process is None or job.status != "running" or job.process.poll() is not None:
                return False
            if os.name == "nt":
                result = subprocess.run(["taskkill", "/PID", str(job.process.pid), "/T", "/F"],
                                        capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                if result.returncode != 0:
                    return False
            else:
                try:
                    os.killpg(job.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    return False
            job.status = "stopped"
            job.finished_at = datetime.now(timezone.utc).isoformat()
            self._persist(job)
        if job.kind == "reindex":
            with self._reindex_lock:
                self._reindex_pending.discard(str(job.project_dir))
        return True


registry = JobRegistry()
