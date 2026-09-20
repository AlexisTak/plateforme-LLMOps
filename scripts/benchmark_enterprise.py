"""CPU-only comparison of approval lookup paths, using an isolated temporary DB.

Run: PYTHONPATH=. .venv/bin/python scripts/benchmark_enterprise.py
"""
import json
import statistics
import tempfile
import time
from pathlib import Path

from api.enterprise import EnterpriseStore


def measure(work):
    samples = []
    for _ in range(15):
        started = time.perf_counter()
        work()
        samples.append((time.perf_counter() - started) * 1000)
    return round(statistics.median(samples), 3)


def main():
    with tempfile.TemporaryDirectory(prefix="openagent-perf-") as directory:
        store = EnterpriseStore(Path(directory) / "benchmark.db")
        tool = store.set_tool("demo", "lookup", "GET", "https://example.test", False, 5, 1000)
        with store._connect() as db:
            db.executemany("INSERT INTO approvals VALUES (?,?,?,?,?,?,?,?,?,?)", (
                (str(i), "demo", tool["id"], "demo-user", "pending", '{"query":"demo"}',
                 None, f"2026-01-01T00:00:{i:05}", None, None) for i in range(10000)
            ))
        def previous():
            return next(item for item in store.approvals("demo") if item["id"] == "0")

        def optimized():
            return store.approval("demo", "0")

        assert previous() == optimized()
        before, after = measure(previous), measure(optimized)
        print(json.dumps({"rows": 10000, "samples": 15, "median_ms_previous": before,
                          "median_ms_optimized": after, "speedup": round(before / after, 1)}, indent=2))


if __name__ == "__main__":
    main()
