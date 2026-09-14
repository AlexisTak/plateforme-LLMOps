from api.opportunities_scoring import compute_score, kpi_status

ZERO = {"market": 0, "profitability": 0, "feasibility": 0, "commercialization": 0,
        "scalability": 0, "retention": 0, "risk": 0}


def test_compute_score_priorite_strategique_at_85():
    scores = {**ZERO, "market": 20, "profitability": 20, "feasibility": 15,
              "commercialization": 15, "scalability": 15}
    result = compute_score(scores)
    assert result["total"] == 85
    assert result["label"] == "priorite_strategique"


def test_compute_score_matches_seed_ranking_example():
    scores = {"market": 15, "profitability": 17, "feasibility": 13, "commercialization": 11,
              "scalability": 14, "retention": 9, "risk": 5}
    result = compute_score(scores)
    assert result["total"] == 84
    assert result["label"] == "tres_interessant"
    assert result["breakdown"] == scores


def test_compute_score_a_eviter_at_zero():
    assert compute_score(ZERO)["label"] == "a_eviter"


def test_kpi_status_atteint_when_lower_is_better_and_below_target():
    kpi = {"current_value": 2.1, "previous_value": 2.6, "target_value": 3, "higher_is_better": False}
    result = kpi_status(kpi)
    assert result["status"] == "atteint"
    assert result["trend"] == "baisse"


def test_kpi_status_attention_within_10_percent_of_target():
    kpi = {"current_value": 18500, "previous_value": 16500, "target_value": 20000, "higher_is_better": True}
    result = kpi_status(kpi)
    assert result["status"] == "attention"
    assert round(result["evolution_pct"], 2) == 12.12
    assert result["trend"] == "hausse"


def test_kpi_status_non_atteint_far_from_target():
    kpi = {"current_value": 5, "previous_value": 5, "target_value": 50, "higher_is_better": True}
    result = kpi_status(kpi)
    assert result["status"] == "non_atteint"
    assert result["trend"] == "stable"


def test_kpi_status_inconnu_without_values():
    kpi = {"current_value": None, "previous_value": None, "target_value": None, "higher_is_better": True}
    assert kpi_status(kpi)["status"] == "inconnu"
