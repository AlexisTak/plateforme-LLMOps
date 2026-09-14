// web/src/app/opportunities/[id]/page.tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  api, Opportunity, OpportunityAnalysis, OpportunityFields, OpportunityKpi, OpportunityScores,
  Project, Provider, SCORE_LABELS,
} from "@/lib/api";
import { simulate, SimulatorInput } from "@/lib/simulator";
import { Button, Card, EmptyState, PageHeader, Pill, SectionTitle } from "@/components/ui";

const STATUSES: Opportunity["status"][] = [
  "idee", "analyse", "validation", "poc", "pilote", "commercialisation", "production", "abandonnee",
];
function labelForTotal(total: number): Opportunity["score"]["label"] {
  if (total >= 85) return "priorite_strategique";
  if (total >= 70) return "tres_interessant";
  if (total >= 55) return "a_tester";
  if (total >= 40) return "risque";
  return "a_eviter";
}
const SCORE_FIELDS: { key: keyof OpportunityScores; label: string; max: number }[] = [
  { key: "market", label: "Marché", max: 20 },
  { key: "profitability", label: "Rentabilité", max: 20 },
  { key: "feasibility", label: "Faisabilité", max: 15 },
  { key: "commercialization", label: "Commercialisation", max: 15 },
  { key: "scalability", label: "Scalabilité", max: 15 },
  { key: "retention", label: "Rétention", max: 10 },
  { key: "risk", label: "Risque (5 = aucun risque)", max: 5 },
];

export default function OpportunityDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [fields, setFields] = useState<OpportunityFields | null>(null);
  const [status, setStatus] = useState<Opportunity["status"]>("idee");
  const [scores, setScores] = useState<OpportunityScores | null>(null);
  const [kpis, setKpis] = useState<OpportunityKpi[]>([]);
  const [analyses, setAnalyses] = useState<OpportunityAnalysis[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [analysisProjectId, setAnalysisProjectId] = useState("");
  const [analysisProviderId, setAnalysisProviderId] = useState("");
  const [simInput, setSimInput] = useState<SimulatorInput | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const [item, kpiList, analysisList, projectList] = await Promise.all([
      api.opportunities.get(id), api.opportunities.kpis(id), api.opportunities.analyses(id), api.projects.list(),
    ]);
    setFields(item);
    setStatus(item.status);
    setScores(item.scores);
    setKpis(kpiList);
    setAnalyses(analysisList);
    setProjects(projectList);
    setSimInput((current) => current ?? {
      setupPrice: item.setup_price, monthlyPrice: item.monthly_price, clients: 10,
      humanCost: 0, infraCost: item.monthly_cost, llmCost: 0, cac: 0, churnPct: 0, salesCost: 0,
    });
  }, [id]);

  useEffect(() => { refresh().catch((e) => setError(String(e))); }, [refresh]);

  useEffect(() => {
    if (!analysisProjectId) { setProviders([]); return; }
    api.enterprise.providers(analysisProjectId).then((list) => setProviders(list.filter((p) => p.enabled)))
      .catch((e) => setError(String(e)));
  }, [analysisProjectId]);

  const act = async (work: () => Promise<unknown>) => {
    setBusy(true); setError(null);
    try { await work(); await refresh(); } catch (e) { setError(String(e)); } finally { setBusy(false); }
  };

  if (error && (!fields || !scores)) {
    return <Card className="border-error/30 bg-error-soft text-error text-sm">{error}</Card>;
  }
  if (!fields || !scores) return <p>Chargement…</p>;

  const total = SCORE_FIELDS.reduce((sum, f) => sum + scores[f.key], 0);
  const label = SCORE_LABELS[labelForTotal(total)];

  return <div className="space-y-8">
    <PageHeader title={fields.name} description={fields.value_proposition}
      action={<select value={status} disabled={busy}
        onChange={(e) => act(() => api.opportunities.updateStatus(id, e.target.value as Opportunity["status"]))}
        className="bg-bg border border-border rounded-md px-2 py-1 text-xs">
        {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
      </select>} />
    {error ? <Card className="border-error/30 bg-error-soft text-error text-sm">{error}</Card> : null}

    <section>
      <SectionTitle>Fiche opportunité</SectionTitle>
      <Card className="grid gap-3 md:grid-cols-2">
        <Field label="Nom"><TextField value={fields.name} onChange={(v) => setFields({ ...fields, name: v })} /></Field>
        <Field label="Secteur"><TextField value={fields.sector} onChange={(v) => setFields({ ...fields, sector: v })} /></Field>
        <Field label="Cible"><TextField value={fields.target_customer} onChange={(v) => setFields({ ...fields, target_customer: v })} /></Field>
        <Field label="Modèle économique"><TextField value={fields.business_model} onChange={(v) => setFields({ ...fields, business_model: v })} /></Field>
        <Field label="Problème client" full><Textarea value={fields.customer_problem} onChange={(v) => setFields({ ...fields, customer_problem: v })} /></Field>
        <Field label="Solution proposée" full><Textarea value={fields.proposed_solution} onChange={(v) => setFields({ ...fields, proposed_solution: v })} /></Field>
        <Field label="Proposition de valeur" full><Textarea value={fields.value_proposition} onChange={(v) => setFields({ ...fields, value_proposition: v })} /></Field>
        <Field label="Différenciation" full><Textarea value={fields.differentiation} onChange={(v) => setFields({ ...fields, differentiation: v })} /></Field>
        <Field label="Coût de setup (€)"><NumberField value={fields.setup_cost} onChange={(v) => setFields({ ...fields, setup_cost: v })} /></Field>
        <Field label="Coût mensuel (€)"><NumberField value={fields.monthly_cost} onChange={(v) => setFields({ ...fields, monthly_cost: v })} /></Field>
        <Field label="Prix de setup (€)"><NumberField value={fields.setup_price} onChange={(v) => setFields({ ...fields, setup_price: v })} /></Field>
        <Field label="Abonnement mensuel (€)"><NumberField value={fields.monthly_price} onChange={(v) => setFields({ ...fields, monthly_price: v })} /></Field>
        <div className="md:col-span-2"><Button variant="accent" disabled={busy} onClick={() => act(() => api.opportunities.update(id, fields))}>Enregistrer la fiche</Button></div>
      </Card>
    </section>

    <section>
      <SectionTitle>Score — {label.emoji} {label.text} · {total}/100</SectionTitle>
      <Card className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {SCORE_FIELDS.map((f) => <label key={f.key} className="text-xs text-text-muted">
          {f.label} (0–{f.max})
          <input type="number" min={0} max={f.max} value={scores[f.key]}
            onChange={(e) => setScores({ ...scores, [f.key]: Math.max(0, Math.min(f.max, Number(e.target.value))) })}
            className="mt-1 w-full bg-bg border border-border rounded-md px-3 py-1.5 text-sm text-text-primary" />
        </label>)}
        <div className="lg:col-span-4"><Button variant="accent" disabled={busy} onClick={() => act(() => api.opportunities.updateScores(id, scores))}>Enregistrer le score</Button></div>
      </Card>
    </section>

    <section>
      <SectionTitle>KPI</SectionTitle>
      {kpis.length === 0 ? <EmptyState>Aucun KPI défini.</EmptyState> : <div className="space-y-2">
        {kpis.map((kpi) => <KpiRow key={kpi.id} kpi={kpi} busy={busy}
          onSave={(current, target) => act(() => api.opportunities.upsertKpi(id, {
            name: kpi.name, category: kpi.category, unit: kpi.unit,
            current_value: current, target_value: target, higher_is_better: !!kpi.higher_is_better,
          }))} />)}
      </div>}
    </section>

    {simInput ? <section>
      <SectionTitle>Simulateur financier</SectionTitle>
      <SimulatorPanel input={simInput} onChange={setSimInput} />
    </section> : null}

    <section>
      <SectionTitle>Analyse IA</SectionTitle>
      <Card className="flex flex-wrap gap-2 items-end mb-3">
        <label className="text-xs text-text-muted">Projet
          <select value={analysisProjectId} onChange={(e) => setAnalysisProjectId(e.target.value)}
            className="mt-1 block bg-bg border border-border rounded-md px-2 py-1.5 text-sm">
            <option value="">—</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
          </select>
        </label>
        <label className="text-xs text-text-muted">Fournisseur
          <select value={analysisProviderId} onChange={(e) => setAnalysisProviderId(e.target.value)}
            className="mt-1 block bg-bg border border-border rounded-md px-2 py-1.5 text-sm">
            <option value="">—</option>
            {providers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </label>
        <Button variant="accent" disabled={busy || !analysisProjectId || !analysisProviderId}
          onClick={() => act(() => api.opportunities.analyze(id, analysisProjectId, analysisProviderId))}>
          Analyser avec l’IA
        </Button>
      </Card>
      {analyses.length === 0 ? <EmptyState>Aucune analyse pour l’instant.</EmptyState> : <AnalysisView analysis={analyses[0]} />}
    </section>
  </div>;
}

function Field({ label, children, full }: { label: string; children: React.ReactNode; full?: boolean }) {
  return <label className={`text-xs text-text-muted ${full ? "md:col-span-2" : ""}`}>{label}<div className="mt-1">{children}</div></label>;
}
function TextField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return <input value={value} onChange={(e) => onChange(e.target.value)}
    className="w-full bg-bg border border-border rounded-md px-3 py-1.5 text-sm text-text-primary" />;
}
function Textarea({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return <textarea value={value} onChange={(e) => onChange(e.target.value)} rows={2}
    className="w-full bg-bg border border-border rounded-md px-3 py-1.5 text-sm text-text-primary" />;
}
function NumberField({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return <input type="number" value={value} onChange={(e) => onChange(Number(e.target.value))}
    className="w-full bg-bg border border-border rounded-md px-3 py-1.5 text-sm text-text-primary" />;
}

function KpiRow({ kpi, busy, onSave }: { kpi: OpportunityKpi; busy: boolean; onSave: (current: number | null, target: number | null) => void }) {
  const [current, setCurrent] = useState(kpi.current_value ?? 0);
  const [target, setTarget] = useState(kpi.target_value ?? 0);
  const statusDot = kpi.status === "atteint" ? "🟢" : kpi.status === "attention" ? "🟠" : kpi.status === "non_atteint" ? "🔴" : "⚪";
  return <Card className="flex flex-wrap items-center justify-between gap-3">
    <div>
      <p className="text-sm text-text-primary">{statusDot} {kpi.name} <Pill>{kpi.category}</Pill></p>
      <p className="text-xs text-text-muted mt-1">
        {kpi.evolution_pct != null ? `${kpi.evolution_pct > 0 ? "+" : ""}${kpi.evolution_pct.toFixed(1)}% · ${kpi.trend}` : "Pas d’historique"}
      </p>
    </div>
    <div className="flex items-center gap-2">
      <input type="number" value={current} onChange={(e) => setCurrent(Number(e.target.value))} className="w-24 bg-bg border border-border rounded-md px-2 py-1 text-sm" />
      <span className="text-xs text-text-muted">/ objectif</span>
      <input type="number" value={target} onChange={(e) => setTarget(Number(e.target.value))} className="w-24 bg-bg border border-border rounded-md px-2 py-1 text-sm" />
      <Button disabled={busy} onClick={() => onSave(current, target)}>Mesurer</Button>
    </div>
  </Card>;
}

function SimulatorPanel({ input, onChange }: { input: SimulatorInput; onChange: (v: SimulatorInput) => void }) {
  const result = simulate(input);
  const fields: { key: keyof SimulatorInput; label: string }[] = [
    { key: "setupPrice", label: "Prix setup (€)" }, { key: "monthlyPrice", label: "Abonnement (€/mois)" },
    { key: "clients", label: "Nombre de clients" }, { key: "humanCost", label: "Coût humain (€/mois)" },
    { key: "infraCost", label: "Coût infra (€/mois/client)" }, { key: "llmCost", label: "Coût LLM (€/mois/client)" },
    { key: "cac", label: "CAC (€/client)" }, { key: "churnPct", label: "Churn (%)" },
    { key: "salesCost", label: "Coût commercial (€/mois)" },
  ];
  return <Card className="space-y-4">
    <div className="grid gap-3 sm:grid-cols-3">
      {fields.map((f) => <label key={f.key} className="text-xs text-text-muted">{f.label}
        <input type="number" value={input[f.key]} onChange={(e) => onChange({ ...input, [f.key]: Number(e.target.value) })}
          className="mt-1 w-full bg-bg border border-border rounded-md px-3 py-1.5 text-sm text-text-primary" />
      </label>)}
    </div>
    <div className="grid gap-3 sm:grid-cols-3 text-sm border-t border-border pt-4">
      <Metric label="CA mensuel" value={`${result.monthlyRevenue.toLocaleString("fr-FR")} €`} />
      <Metric label="CA annuel" value={`${result.annualRevenue.toLocaleString("fr-FR")} €`} />
      <Metric label="MRR" value={`${result.mrr.toLocaleString("fr-FR")} €`} />
      <Metric label="ARR" value={`${result.arr.toLocaleString("fr-FR")} €`} />
      <Metric label="Marge brute" value={`${result.grossMargin.toLocaleString("fr-FR")} €`} />
      <Metric label="Marge nette (estim.)" value={`${result.netMarginEstimate.toLocaleString("fr-FR")} €`} />
      <Metric label="Break-even" value={result.breakEvenMonths == null ? "jamais" : `${result.breakEvenMonths} mois`} />
      <Metric label="ROI" value={result.roi == null ? "n/a" : `${result.roi.toFixed(0)} %`} />
      <Metric label="Clients pour 100k€" value={result.clientsFor100k == null ? "n/a" : `${result.clientsFor100k}`} />
      <Metric label="Clients pour 500k€" value={result.clientsFor500k == null ? "n/a" : `${result.clientsFor500k}`} />
      <Metric label="Clients pour 1M€" value={result.clientsFor1M == null ? "n/a" : `${result.clientsFor1M}`} />
    </div>
  </Card>;
}
function Metric({ label, value }: { label: string; value: string }) {
  return <div><p className="text-xs uppercase tracking-wide text-text-muted">{label}</p><p className="font-mono mt-1">{value}</p></div>;
}

function AnalysisView({ analysis }: { analysis: OpportunityAnalysis }) {
  const result = analysis.result as {
    summary?: string; strengths?: string[]; weaknesses?: string[]; risks?: string[];
    recommendations?: string[]; confidence_labels?: Record<string, "verified" | "hypothesis" | "estimate">;
  };
  const item = (text: string) => {
    const confidence = result.confidence_labels?.[text];
    const style = confidence === "verified" ? "text-success" : confidence === "hypothesis" ? "text-text-muted" : "text-info";
    return <li key={text} className={style}>{text}</li>;
  };
  return <Card className="space-y-3">
    <p className="text-sm text-text-secondary">{result.summary}</p>
    <div className="grid gap-3 sm:grid-cols-2">
      <div><p className="text-xs uppercase text-text-muted mb-1">Forces</p><ul className="text-sm space-y-1">{(result.strengths ?? []).map(item)}</ul></div>
      <div><p className="text-xs uppercase text-text-muted mb-1">Faiblesses</p><ul className="text-sm space-y-1">{(result.weaknesses ?? []).map(item)}</ul></div>
      <div><p className="text-xs uppercase text-text-muted mb-1">Risques</p><ul className="text-sm space-y-1">{(result.risks ?? []).map(item)}</ul></div>
      <div><p className="text-xs uppercase text-text-muted mb-1">Recommandations</p><ul className="text-sm space-y-1">{(result.recommendations ?? []).map(item)}</ul></div>
    </div>
    <p className="text-xs text-text-muted">Score recommandé par l’IA : {analysis.recommended_score ?? "n/a"}/100 — fournisseur {analysis.provider_id}</p>
  </Card>;
}
