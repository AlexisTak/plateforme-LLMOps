# tests/test_opportunities_routes.py
from fastapi.testclient import TestClient

from api.main import app

SAMPLE_PAYLOAD = {
    "name": "Offre de test", "description": "d", "customer_problem": "p",
    "proposed_solution": "s", "target_customer": "t", "sector": "sec",
    "value_proposition": "v", "technologies": ["LLM"], "maturity": "idee",
    "dev_difficulty": 3, "sales_difficulty": 3, "competition": "c",
    "differentiation": "diff", "business_model": "bm", "setup_cost": 1000,
    "monthly_cost": 100, "setup_price": 2000, "monthly_price": 300,
    "estimated_margin_pct": 40, "recurring_revenue_potential": 3600,
    "risks": ["r1"], "regulatory_constraints": "rgpd",
}


def test_opportunities_are_seeded_and_listed():
    client = TestClient(app)
    response = client.get("/api/opportunities")
    assert response.status_code == 200
    names = {item["name"] for item in response.json()}
    assert "IA Enterprise souveraine" in names


def test_create_score_status_kpi_delete_flow():
    client = TestClient(app)
    created = client.post("/api/opportunities", json=SAMPLE_PAYLOAD).json()
    assert created["score"]["total"] == 0

    scores = {"market": 10, "profitability": 10, "feasibility": 8, "commercialization": 8,
              "scalability": 8, "retention": 5, "risk": 3}
    scored = client.put(f"/api/opportunities/{created['id']}/scores", json=scores).json()
    assert scored["score"]["total"] == 52
    assert scored["score"]["label"] == "risque"

    status = client.put(f"/api/opportunities/{created['id']}/status", json={"status": "poc"}).json()
    assert status["status"] == "poc"

    kpi = client.put(f"/api/opportunities/{created['id']}/kpis", json={
        "name": "MRR", "category": "financier", "unit": "€",
        "current_value": 1000, "target_value": 2000, "higher_is_better": True,
    }).json()
    assert kpi["status"] == "non_atteint"

    deleted = client.delete(f"/api/opportunities/{created['id']}").json()
    assert deleted["deleted"] is True
    assert client.get(f"/api/opportunities/{created['id']}").status_code == 404


def test_dashboard_sorted_by_score_desc():
    client = TestClient(app)
    totals = [item["score"]["total"] for item in client.get("/api/opportunities/dashboard").json()]
    assert totals == sorted(totals, reverse=True)


def test_analyze_requires_known_provider():
    client = TestClient(app)
    opportunity_id = client.get("/api/opportunities").json()[0]["id"]
    response = client.post(f"/api/opportunities/{opportunity_id}/analyze",
                            json={"project_id": "no-such-project", "provider_id": "no-such-provider"})
    assert response.status_code == 404


def test_analyze_returns_502_on_malformed_llm_response(monkeypatch):
    client = TestClient(app)
    provider = client.put("/api/enterprise/projects/assistant/providers", json={
        "name": "Test malformed", "type": "ollama", "base_url": "http://localhost:11434",
        "model": "llama:3b", "api_key_env": None, "enabled": True,
    }).json()

    # Valid JSON, no fence — parses fine but isn't a dict. Pre-fix, `parsed.get(...)`
    # then crashes with AttributeError on a list (unhandled 500); post-fix, the
    # isinstance(parsed, dict) check catches it and returns a clean 502.
    monkeypatch.setattr("api.routes.opportunities.generate", lambda provider, prompt: "[1,2,3]")

    opportunity_id = client.get("/api/opportunities").json()[0]["id"]
    response = client.post(f"/api/opportunities/{opportunity_id}/analyze",
                            json={"project_id": "assistant", "provider_id": provider["id"]})
    assert response.status_code == 502

    client.delete(f"/api/enterprise/projects/assistant/providers/{provider['id']}")
