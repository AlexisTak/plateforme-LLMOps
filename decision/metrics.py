"""Classification metrics for Decision Models (mission §6) — pure functions,
no ML framework dependency (small closed label sets, no need for sklearn)."""

from __future__ import annotations

from datetime import UTC, datetime

from api.schemas import DecisionClassMetric, DecisionConfusionRow, DecisionEvaluationResult

INVALID = "__invalid__"  # sentinel for a prediction that failed schema validation


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(pct / 100 * (len(ordered) - 1))))
    return ordered[index]


def evaluate(pairs: list[tuple[str, str]], labels: list[str], latencies_ms: list[float]) -> DecisionEvaluationResult:
    """pairs: list of (actual, predicted) where predicted may be INVALID."""
    n = len(pairs)
    invalid = sum(1 for _, pred in pairs if pred == INVALID)
    correct = sum(1 for actual, pred in pairs if actual == pred)

    matrix: dict[str, dict[str, int]] = {label: {other: 0 for other in [*labels, INVALID]} for label in labels}
    for actual, pred in pairs:
        if actual in matrix:
            matrix[actual][pred] = matrix[actual].get(pred, 0) + 1

    per_class: list[DecisionClassMetric] = []
    precisions, recalls, f1s = [], [], []
    for label in labels:
        tp = matrix[label][label]
        support = sum(matrix[label].values())
        predicted_as_label = sum(matrix[other].get(label, 0) for other in labels)
        precision = tp / predicted_as_label if predicted_as_label else 0.0
        recall = tp / support if support else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        per_class.append(DecisionClassMetric(decision=label, precision=precision, recall=recall, f1=f1, support=support))
        precisions.append(precision)
        recalls.append(recall)
        f1s.append(f1)

    confusion_matrix = [DecisionConfusionRow(actual=label, predicted=matrix[label]) for label in labels]

    return DecisionEvaluationResult(
        n=n,
        accuracy=correct / n if n else 0.0,
        macro_precision=sum(precisions) / len(precisions) if precisions else 0.0,
        macro_recall=sum(recalls) / len(recalls) if recalls else 0.0,
        macro_f1=sum(f1s) / len(f1s) if f1s else 0.0,
        invalid_output_rate=invalid / n if n else 0.0,
        per_class=per_class,
        confusion_matrix=confusion_matrix,
        latency_ms_p50=_percentile(latencies_ms, 50),
        latency_ms_p95=_percentile(latencies_ms, 95),
        generated_at=datetime.now(UTC).isoformat(),
    )
