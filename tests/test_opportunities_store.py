# tests/test_opportunities_store.py
from pathlib import Path

from api.enterprise import Actor, EnterpriseStore
from api.opportunities_scoring import compute_score


def _sample_data() -> dict:
    return {
        "name": "Test Opportunity", "description": "d", "customer_problem": "p",
        "proposed_solution": "s", "target_customer": "t", "sector": "sec",
        "value_proposition": "v", "technologies": ["LLM"], "maturity": "idee",
        "dev_difficulty": 3, "sales_difficulty": 3, "competition": "c",
        "differentiation": "diff", "business_model": "bm", "setup_cost": 1000,
        "monthly_cost": 100, "setup_price": 2000, "monthly_price": 300,
        "estimated_margin_pct": 40, "recurring_revenue_potential": 3600,
        "risks": ["r1"], "regulatory_constraints": "rgpd",
    }


def test_create_and_get_opportunity_round_trips_json_fields(tmp_path: Path):
    control = EnterpriseStore(tmp_path / "enterprise.db")
    actor = Actor("alice", "alice@example.test", "admin", "Alice")
    created = control.create_opportunity(_sample_data(), actor)
    fetched = control.get_opportunity(created["id"])
    assert fetched["technologies"] == ["LLM"]
    assert fetched["risks"] == ["r1"]
    assert fetched["scores"] == {"market": 0, "profitability": 0, "feasibility": 0,
                                  "commercialization": 0, "scalability": 0, "retention": 0, "risk": 0}
    assert fetched["status"] == "idee"


def test_update_opportunity_scores_and_status(tmp_path: Path):
    control = EnterpriseStore(tmp_path / "enterprise.db")
    actor = Actor("alice", "alice@example.test", "admin", "Alice")
    created = control.create_opportunity(_sample_data(), actor)
    scores = {"market": 17, "profitability": 17, "feasibility": 13, "commercialization": 13,
              "scalability": 13, "retention": 9, "risk": 5}
    updated = control.update_opportunity_scores(created["id"], scores)
    assert updated["scores"] == scores
    updated = control.update_opportunity_status(created["id"], "poc")
    assert updated["status"] == "poc"


def test_upsert_kpi_shifts_current_to_previous(tmp_path: Path):
    control = EnterpriseStore(tmp_path / "enterprise.db")
    actor = Actor("alice", "alice@example.test", "admin", "Alice")
    created = control.create_opportunity(_sample_data(), actor)
    control.upsert_kpi(created["id"], "MRR", "financier", "€", 16500, 20000, True)
    second = control.upsert_kpi(created["id"], "MRR", "financier", "€", 18500, 20000, True)
    assert second["current_value"] == 18500
    assert second["previous_value"] == 16500
    assert len(control.list_kpis(created["id"])) == 1


def test_delete_opportunity(tmp_path: Path):
    control = EnterpriseStore(tmp_path / "enterprise.db")
    actor = Actor("alice", "alice@example.test", "admin", "Alice")
    created = control.create_opportunity(_sample_data(), actor)
    assert control.delete_opportunity(created["id"])
    assert control.get_opportunity(created["id"]) is None


def test_seed_creates_five_opportunities_matching_ranking(tmp_path: Path):
    control = EnterpriseStore(tmp_path / "enterprise.db")
    opportunities = control.list_opportunities()
    assert len(opportunities) == 5
    totals = sorted((compute_score(o["scores"])["total"] for o in opportunities), reverse=True)
    assert totals == [87, 84, 79, 76, 73]
    names = {o["name"] for o in opportunities}
    assert names == {"IA Enterprise souveraine", "RAG-as-a-Service", "AI Agents Business",
                      "AI Modernization", "AI Continuous Improvement"}


def test_ai_analysis_round_trip(tmp_path: Path):
    control = EnterpriseStore(tmp_path / "enterprise.db")
    actor = Actor("alice", "alice@example.test", "admin", "Alice")
    created = control.create_opportunity(_sample_data(), actor)
    control.save_ai_analysis(created["id"], "demo-project", "provider-1", {"summary": "ok"}, 70, actor.id)
    analyses = control.list_ai_analyses(created["id"])
    assert analyses[0]["result"] == {"summary": "ok"}
    assert analyses[0]["recommended_score"] == 70
