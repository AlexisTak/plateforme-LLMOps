from __future__ import annotations

from typing import Any

SCORE_MAX = {
    "market": 20, "profitability": 20, "feasibility": 15, "commercialization": 15,
    "scalability": 15, "retention": 10, "risk": 5,
}


def compute_score(scores: dict[str, int]) -> dict[str, Any]:
    total = sum(scores[key] for key in SCORE_MAX)
    if total >= 85:
        label = "priorite_strategique"
    elif total >= 70:
        label = "tres_interessant"
    elif total >= 55:
        label = "a_tester"
    elif total >= 40:
        label = "risque"
    else:
        label = "a_eviter"
    return {"total": total, "label": label, "breakdown": scores}


def kpi_status(kpi: dict[str, Any]) -> dict[str, Any]:
    current = kpi.get("current_value")
    previous = kpi.get("previous_value")
    target = kpi.get("target_value")
    higher_is_better = kpi.get("higher_is_better", True)

    evolution_pct = None
    if previous not in (None, 0) and current is not None:
        evolution_pct = (current - previous) / abs(previous) * 100

    if not evolution_pct:
        trend = "stable"
    elif evolution_pct > 0:
        trend = "hausse"
    else:
        trend = "baisse"

    if current is None or target is None:
        status = "inconnu"
    else:
        reached = current >= target if higher_is_better else current <= target
        near = abs(current - target) <= 0.1 * abs(target or 1)
        status = "atteint" if reached else ("attention" if near else "non_atteint")

    return {**kpi, "evolution_pct": evolution_pct, "trend": trend, "status": status}
