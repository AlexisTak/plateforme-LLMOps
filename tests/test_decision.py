"""Decision Model tests: schema validation, dataset validation, metrics
(confusion matrix / F1 / invalid rate), gateway output parsing, and the
registry/fallback HTTP surface. See mission §19."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.paths import project_dir
from api.routes import decision
from api.schemas import DecisionSchema
from decision import dataset as decision_dataset
from decision import gateway
from decision import metrics as decision_metrics


def _client(project: Path) -> TestClient:
    app = FastAPI()
    app.include_router(decision.router)
    app.dependency_overrides[project_dir] = lambda: project
    return TestClient(app)


def _make_project(tmp_path: Path) -> Path:
    project = tmp_path / "ticket-router"
    (project / "decision" / "dataset").mkdir(parents=True)
    return project


# ---------------------------------------------------------------------------
# DecisionSchema validation


def test_decision_schema_rejects_duplicate_decisions():
    with pytest.raises(ValidationError):
        DecisionSchema(name="Router", decisions=["billing", "billing", "technical"])


def test_decision_schema_rejects_empty_decision_value():
    with pytest.raises(ValidationError):
        DecisionSchema(name="Router", decisions=["billing", ""])


def test_decision_schema_requires_at_least_two_decisions():
    with pytest.raises(ValidationError):
        DecisionSchema(name="Router", decisions=["billing"])


# ---------------------------------------------------------------------------
# Dataset validation (mission §4: allowed decision, missing fields, doublons)


def test_dataset_validate_flags_disallowed_decision(tmp_path: Path):
    project = _make_project(tmp_path)
    schema = DecisionSchema(name="Router", decisions=["billing", "technical"])
    decision_dataset.append_example(project, "train", "mon paiement a été débité deux fois", "billing")
    decision_dataset.append_example(project, "train", "je veux un remboursement", "refund")  # not in schema

    result = decision_dataset.validate(project, schema)
    assert result.errors == 1
    assert any("hors du schema" in f.message for f in result.findings)


def test_dataset_validate_flags_near_duplicate_input(tmp_path: Path):
    project = _make_project(tmp_path)
    schema = DecisionSchema(name="Router", decisions=["billing", "technical"])
    decision_dataset.append_example(project, "train", "Mon paiement a été débité deux fois", "billing")
    decision_dataset.append_example(project, "validation", "mon paiement a été débité deux fois", "billing")

    result = decision_dataset.validate(project, schema)
    assert result.warnings == 1


def test_dataset_stats_computes_balance_ratio(tmp_path: Path):
    project = _make_project(tmp_path)
    for _ in range(3):
        decision_dataset.append_example(project, "train", "a", "billing")
    decision_dataset.append_example(project, "train", "b", "technical")

    stats = decision_dataset.stats(project)
    assert stats.total_examples == 4
    assert stats.smallest_class == 1
    assert stats.largest_class == 3
    assert stats.balance_ratio == pytest.approx(1 / 3)


# ---------------------------------------------------------------------------
# Metrics: confusion matrix / precision / recall / F1 / invalid_output_rate


def test_metrics_perfect_classifier():
    pairs = [("billing", "billing"), ("technical", "technical"), ("billing", "billing")]
    result = decision_metrics.evaluate(pairs, ["billing", "technical"], latencies_ms=[10, 12, 11])
    assert result.accuracy == 1.0
    assert result.macro_f1 == 1.0
    assert result.invalid_output_rate == 0.0


def test_metrics_counts_invalid_output_and_confusion():
    pairs = [
        ("billing", "billing"),
        ("billing", "technical"),  # confused
        ("technical", decision_metrics.INVALID),  # model produced an invalid decision
    ]
    result = decision_metrics.evaluate(pairs, ["billing", "technical"], latencies_ms=[5, 5, 5])
    assert result.invalid_output_rate == pytest.approx(1 / 3)
    assert result.accuracy == pytest.approx(1 / 3)
    billing_row = next(row for row in result.confusion_matrix if row.actual == "billing")
    assert billing_row.predicted["technical"] == 1


def test_metrics_empty_pairs_do_not_divide_by_zero():
    result = decision_metrics.evaluate([], ["billing", "technical"], latencies_ms=[])
    assert result.n == 0
    assert result.accuracy == 0.0
    assert result.invalid_output_rate == 0.0


# ---------------------------------------------------------------------------
# Gateway output parsing (mission §3: invalid decision == error, not a valid response)


def test_gateway_parses_valid_json_decision():
    schema = DecisionSchema(name="Router", decisions=["billing", "technical"])
    decision, confidence = gateway._parse_and_validate('{"decision": "billing", "confidence": 0.94}', schema)
    assert decision == "billing"
    assert confidence == pytest.approx(0.94)


def test_gateway_rejects_decision_outside_schema():
    schema = DecisionSchema(name="Router", decisions=["billing", "technical"])
    with pytest.raises(gateway.DecisionError):
        gateway._parse_and_validate('{"decision": "spam"}', schema)


def test_gateway_rejects_non_json_output():
    schema = DecisionSchema(name="Router", decisions=["billing", "technical"])
    with pytest.raises(gateway.DecisionError):
        gateway._parse_and_validate("Je pense que c'est billing.", schema)


def test_gateway_rejects_confidence_out_of_range():
    schema = DecisionSchema(name="Router", decisions=["billing", "technical"])
    with pytest.raises(gateway.DecisionError):
        gateway._parse_and_validate('{"decision": "billing", "confidence": 1.5}', schema)


def test_gateway_strips_markdown_code_fence():
    schema = DecisionSchema(name="Router", decisions=["billing", "technical"])
    decision, _ = gateway._parse_and_validate('```json\n{"decision": "technical"}\n```', schema)
    assert decision == "technical"


# ---------------------------------------------------------------------------
# HTTP surface: schema + dataset CRUD + fallback config (no model inference)


def test_schema_roundtrip_over_http(tmp_path: Path):
    project = _make_project(tmp_path)
    client = _client(project)

    resp = client.put(f"/api/projects/{project.name}/decision/schema", json={
        "name": "Ticket Router", "decisions": ["billing", "technical", "sales", "spam"], "confidence": True,
    })
    assert resp.status_code == 200, resp.text

    resp = client.get(f"/api/projects/{project.name}/decision/schema")
    assert resp.status_code == 200
    assert resp.json()["decisions"] == ["billing", "technical", "sales", "spam"]


def test_dataset_crud_over_http(tmp_path: Path):
    project = _make_project(tmp_path)
    client = _client(project)

    resp = client.post(f"/api/projects/{project.name}/decision/dataset", json={
        "file": "train.jsonl", "input": "je n'arrive plus à me connecter", "decision": "technical",
    })
    assert resp.status_code == 200, resp.text
    example = resp.json()

    resp = client.get(f"/api/projects/{project.name}/decision/dataset/train")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    resp = client.delete(f"/api/projects/{project.name}/decision/dataset/train/{example['index']}")
    assert resp.status_code == 200
    assert client.get(f"/api/projects/{project.name}/decision/dataset/train").json() == []


def test_dataset_route_rejects_unknown_split(tmp_path: Path):
    project = _make_project(tmp_path)
    client = _client(project)
    resp = client.get(f"/api/projects/{project.name}/decision/dataset/../secret")
    assert resp.status_code in (400, 404)


def test_fallback_config_roundtrip_over_http(tmp_path: Path):
    project = _make_project(tmp_path)
    client = _client(project)

    resp = client.put(f"/api/projects/{project.name}/decision/fallback", json={
        "enabled": True, "fallback_project_id": "generalist-assistant", "threshold": 0.85,
    })
    assert resp.status_code == 200, resp.text

    resp = client.get(f"/api/projects/{project.name}/decision/fallback")
    assert resp.json()["fallback_project_id"] == "generalist-assistant"
    assert resp.json()["threshold"] == 0.85


def test_evaluate_rejects_empty_test_split(tmp_path: Path):
    project = _make_project(tmp_path)
    client = _client(project)
    client.put(f"/api/projects/{project.name}/decision/schema", json={
        "name": "Router", "decisions": ["billing", "technical"], "confidence": True,
    })
    resp = client.post(f"/api/projects/{project.name}/decision/evaluate")
    assert resp.status_code == 409
