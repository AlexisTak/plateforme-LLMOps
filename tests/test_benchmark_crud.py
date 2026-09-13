import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.paths import project_dir
from api.routes import evaluation


def _case(case_id: str = "hello") -> dict:
    return {"id": case_id, "category": "quality", "user": "Dis bonjour", "checks": {
        "expect_json": False, "expect_keys": [], "max_chars": 120, "expect_plain_text": True,
    }, "review": ["Réponse pertinente"]}


def test_benchmark_crud_preserves_jsonl(tmp_path: Path):
    path = tmp_path / "evaluation" / "benchmark.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(_case("existing")) + "\n", encoding="utf-8")
    app = FastAPI()
    app.include_router(evaluation.router)
    app.dependency_overrides[project_dir] = lambda: tmp_path
    client = TestClient(app)

    assert client.post("/api/projects/demo/evaluation/benchmark", json=_case()).status_code == 201
    assert client.post("/api/projects/demo/evaluation/benchmark", json=_case()).status_code == 409
    edited = _case("renamed")
    edited["user"] = "Présente-toi"
    assert client.put("/api/projects/demo/evaluation/benchmark/hello", json=edited).json()["user"] == "Présente-toi"
    assert client.delete("/api/projects/demo/evaluation/benchmark/renamed").json() == {"deleted": True}
    assert [item["id"] for item in client.get("/api/projects/demo/evaluation/benchmark").json()] == ["existing"]


def test_benchmark_crud_validates_inputs(tmp_path: Path):
    path = tmp_path / "evaluation" / "benchmark.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("", encoding="utf-8")
    app = FastAPI()
    app.include_router(evaluation.router)
    app.dependency_overrides[project_dir] = lambda: tmp_path
    invalid = _case("bad id with spaces")
    invalid["review"] = []
    assert TestClient(app).post("/api/projects/demo/evaluation/benchmark", json=invalid).status_code == 422
