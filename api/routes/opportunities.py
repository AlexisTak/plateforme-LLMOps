# api/routes/opportunities.py
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
import requests

from api.ai_provider_client import ProviderCallError, generate
from api.enterprise import actor_from_request, require_role, store
from api.opportunities_scoring import compute_score, kpi_status

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])

STATUSES = ("idee", "analyse", "validation", "poc", "pilote",
            "commercialisation", "production", "abandonnee")


class OpportunityFields(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    customer_problem: str = Field(default="", max_length=4000)
    proposed_solution: str = Field(default="", max_length=4000)
    target_customer: str = Field(default="", max_length=500)
    sector: str = Field(default="", max_length=200)
    value_proposition: str = Field(default="", max_length=2000)
    technologies: list[str] = Field(default_factory=list)
    maturity: str = Field(default="", max_length=100)
    dev_difficulty: int = Field(default=3, ge=1, le=5)
    sales_difficulty: int = Field(default=3, ge=1, le=5)
    competition: str = Field(default="", max_length=2000)
    differentiation: str = Field(default="", max_length=2000)
    business_model: str = Field(default="", max_length=1000)
    setup_cost: float = Field(default=0, ge=0)
    monthly_cost: float = Field(default=0, ge=0)
    setup_price: float = Field(default=0, ge=0)
    monthly_price: float = Field(default=0, ge=0)
    estimated_margin_pct: float = Field(default=0, ge=0, le=100)
    recurring_revenue_potential: float = Field(default=0, ge=0)
    risks: list[str] = Field(default_factory=list)
    regulatory_constraints: str = Field(default="", max_length=2000)


class StatusUpdate(BaseModel):
    status: str = Field(pattern="^(" + "|".join(STATUSES) + ")$")


class ScoresUpdate(BaseModel):
    market: int = Field(ge=0, le=20)
    profitability: int = Field(ge=0, le=20)
    feasibility: int = Field(ge=0, le=15)
    commercialization: int = Field(ge=0, le=15)
    scalability: int = Field(ge=0, le=15)
    retention: int = Field(ge=0, le=10)
    risk: int = Field(ge=0, le=5)


class KpiUpsert(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    category: str = Field(pattern="^(commercial|financier|ia|retention)$")
    unit: str = Field(default="", max_length=30)
    current_value: float | None = None
    target_value: float | None = None
    higher_is_better: bool = True


class AnalyzeRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=200)
    provider_id: str = Field(min_length=1, max_length=100)


def _with_score(opportunity: dict) -> dict:
    return {**opportunity, "score": compute_score(opportunity.pop("scores"))}


def _require_opportunity(opportunity_id: str) -> dict:
    opportunity = store.get_opportunity(opportunity_id)
    if not opportunity:
        raise HTTPException(404, "Opportunité inconnue")
    return opportunity


def _build_analysis_prompt(opportunity: dict, kpis: list[dict]) -> str:
    payload = {"opportunity": opportunity, "kpis": kpis}
    return (
        "Tu es un analyste business IA pour une ESN. Analyse l'opportunité suivante "
        "(JSON ci-dessous) et réponds UNIQUEMENT avec un objet JSON strict ayant "
        "exactement ces clés : summary (string), strengths (liste), weaknesses (liste), "
        "opportunities (liste), risks (liste), competition (string), assumptions (liste), "
        "recommendations (liste), priority_kpis (liste), validation_plan (liste), "
        "recommended_score (entier 0-100), confidence_labels (objet associant chaque "
        "élément textuel ci-dessus à 'verified', 'hypothesis' ou 'estimate' — ne présente "
        "jamais une estimation comme un fait vérifié).\n\n"
        f"Données : {json.dumps(payload, ensure_ascii=False)}"
    )


@router.get("")
def list_opportunities(request: Request):
    require_role(actor_from_request(request), "viewer")
    return [_with_score(o) for o in store.list_opportunities()]


@router.get("/dashboard")
def dashboard(request: Request):
    require_role(actor_from_request(request), "viewer")
    scored = [_with_score(o) for o in store.list_opportunities()]
    scored.sort(key=lambda o: o["score"]["total"], reverse=True)
    return scored


@router.post("", status_code=201)
def create_opportunity(body: OpportunityFields, request: Request):
    current = actor_from_request(request)
    require_role(current, "operator")
    result = store.create_opportunity(body.model_dump(), current)
    store.audit(current.id, "opportunity.created", "opportunity", result["id"], None, {"name": result["name"]})
    return _with_score(result)


@router.get("/{opportunity_id}")
def get_opportunity(opportunity_id: str, request: Request):
    require_role(actor_from_request(request), "viewer")
    return _with_score(_require_opportunity(opportunity_id))


@router.put("/{opportunity_id}")
def update_opportunity(opportunity_id: str, body: OpportunityFields, request: Request):
    current = actor_from_request(request)
    require_role(current, "operator")
    _require_opportunity(opportunity_id)
    result = store.update_opportunity(opportunity_id, body.model_dump())
    store.audit(current.id, "opportunity.updated", "opportunity", opportunity_id, None, {})
    return _with_score(result)


@router.put("/{opportunity_id}/status")
def update_status(opportunity_id: str, body: StatusUpdate, request: Request):
    current = actor_from_request(request)
    require_role(current, "reviewer")
    _require_opportunity(opportunity_id)
    result = store.update_opportunity_status(opportunity_id, body.status)
    store.audit(current.id, "opportunity.status.changed", "opportunity", opportunity_id, None, {"status": body.status})
    return _with_score(result)


@router.put("/{opportunity_id}/scores")
def update_scores(opportunity_id: str, body: ScoresUpdate, request: Request):
    current = actor_from_request(request)
    require_role(current, "operator")
    _require_opportunity(opportunity_id)
    result = store.update_opportunity_scores(opportunity_id, body.model_dump())
    store.audit(current.id, "opportunity.scores.updated", "opportunity", opportunity_id, None, body.model_dump())
    return _with_score(result)


@router.delete("/{opportunity_id}")
def delete_opportunity(opportunity_id: str, request: Request):
    current = actor_from_request(request)
    require_role(current, "admin")
    if not store.delete_opportunity(opportunity_id):
        raise HTTPException(404, "Opportunité inconnue")
    store.audit(current.id, "opportunity.deleted", "opportunity", opportunity_id, None, {})
    return {"deleted": True}


@router.get("/{opportunity_id}/kpis")
def list_kpis(opportunity_id: str, request: Request):
    require_role(actor_from_request(request), "viewer")
    _require_opportunity(opportunity_id)
    return [kpi_status(k) for k in store.list_kpis(opportunity_id)]


@router.put("/{opportunity_id}/kpis")
def upsert_kpi(opportunity_id: str, body: KpiUpsert, request: Request):
    current = actor_from_request(request)
    require_role(current, "operator")
    _require_opportunity(opportunity_id)
    result = store.upsert_kpi(opportunity_id, body.name, body.category, body.unit,
                               body.current_value, body.target_value, body.higher_is_better)
    store.audit(current.id, "opportunity.kpi.updated", "opportunity_kpi", result["id"], None, {"name": body.name})
    return kpi_status(result)


@router.post("/{opportunity_id}/analyze")
def analyze_opportunity(opportunity_id: str, body: AnalyzeRequest, request: Request):
    current = actor_from_request(request)
    require_role(current, "operator")
    opportunity = _require_opportunity(opportunity_id)
    provider = next((p for p in store.providers(body.project_id) if p["id"] == body.provider_id), None)
    if not provider:
        raise HTTPException(404, "Fournisseur inconnu pour ce projet")
    kpis = [kpi_status(k) for k in store.list_kpis(opportunity_id)]
    prompt = _build_analysis_prompt(opportunity, kpis)
    try:
        raw = generate(provider, prompt)
    except (requests.RequestException, ProviderCallError) as exc:
        raise HTTPException(502, f"Appel du fournisseur impossible : {exc}") from exc
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HTTPException(502, "Le fournisseur n’a pas renvoyé de JSON valide") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(502, "Le fournisseur n’a pas renvoyé un objet JSON")
    score = parsed.get("recommended_score")
    if score is not None and (isinstance(score, bool) or not isinstance(score, (int, float))):
        raise HTTPException(502, "Le fournisseur a renvoyé un score invalide")
    result = store.save_ai_analysis(opportunity_id, body.project_id, body.provider_id, parsed,
                                     score, current.id)
    store.audit(current.id, "opportunity.analyzed", "opportunity", opportunity_id, body.project_id,
                {"provider_id": body.provider_id})
    return result


@router.get("/{opportunity_id}/analyses")
def list_analyses(opportunity_id: str, request: Request):
    require_role(actor_from_request(request), "viewer")
    _require_opportunity(opportunity_id)
    return store.list_ai_analyses(opportunity_id)
