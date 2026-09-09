"""Exercise real process-tree cancellation and durable terminal history, without a model."""
import json
from pathlib import Path
import sys
import threading
import time

import psutil
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.jobs import Job, JobRegistry
from scripts import run_with_evaluation


def await_terminal(registry, job, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        path = registry._storage_dir / f"{job.job_id}.json"
        if path.exists() and job.process.poll() is not None:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data["return_code"] is not None:
                return
        threading.Event().wait(0.05)
    pytest.fail("Job did not reach a persisted terminal state")


def test_completed_history_survives_restart(tmp_path):
    registry = JobRegistry(tmp_path / "jobs")
    job = Job("completed", "evaluation", tmp_path, None, None)
    registry._launch(job, [sys.executable, "-c", "print('result')"])
    await_terminal(registry, job)
    restored = JobRegistry(tmp_path / "jobs").get(job.job_id)
    assert restored.status == "completed"
    assert restored.stdout_lines == ["result"]
    assert restored.process is None
    assert restored.project_dir == tmp_path


def test_stop_kills_descendant_and_remains_stopped(tmp_path):
    registry = JobRegistry(tmp_path / "jobs")
    job = Job("stopped", "evaluation", tmp_path, None, None)
    pid_file = tmp_path / "child.pid"
    script = ("import subprocess,sys,time,pathlib; "
              "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)']); "
              f"pathlib.Path({str(pid_file)!r}).write_text(str(child.pid)); "
              "time.sleep(120)")
    registry._launch(job, [sys.executable, "-c", script])
    child_pid = None
    try:
        deadline = time.monotonic() + 10
        while not pid_file.exists() and time.monotonic() < deadline:
            threading.Event().wait(0.05)
        child_pid = int(pid_file.read_text())
        assert registry.stop(job.job_id)
        await_terminal(registry, job)
        assert job.status == "stopped"
        assert not psutil.pid_exists(child_pid)
        assert JobRegistry(tmp_path / "jobs").get(job.job_id).status == "stopped"
        assert not registry.stop(job.job_id)
    finally:
        if job.process.poll() is None:
            registry.stop(job.job_id)
        if child_pid and psutil.pid_exists(child_pid):
            psutil.Process(child_pid).kill()


@pytest.mark.parametrize("training_code,expected_calls", [(0, 2), (1, 1)])
def test_automatic_evaluation_only_follows_success(monkeypatch, tmp_path, training_code, expected_calls):
    calls = []
    def run(command, **kwargs):
        from subprocess import CompletedProcess
        calls.append(command)
        return CompletedProcess(command, training_code if len(calls) == 1 else 0)
    monkeypatch.setattr(run_with_evaluation.subprocess, "run", run)
    monkeypatch.setattr(sys, "argv", ["wrapper", "--project-dir", str(tmp_path), "--", "python", "train.py"])
    if training_code:
        with pytest.raises(SystemExit):
            run_with_evaluation.main()
    else:
        run_with_evaluation.main()
    assert len(calls) == expected_calls
    if expected_calls == 2:
        assert calls[1][-2:] == ["--project-dir", str(tmp_path)]
        assert calls[1][1].endswith("run.py")
