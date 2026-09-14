"use client";

import { useCallback, useEffect, useState } from "react";
import { api, Execution, ExecutionDetail, TraceEvent } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import { Button, Card, EmptyState, PageHeader, Pill, SectionTitle, Skeleton, StatusBadge } from "@/components/ui";
import { humanError } from "@/lib/errors";

const EVENT_LABELS: Record<string, string> = {
  "execution.started": "Exécution démarrée",
  "rag.completed": "Recherche documentaire terminée",
  "generation.first_token": "Premier fragment généré",
  "execution.completed": "Exécution terminée",
  "execution.failed": "Exécution échouée",
};

export default function ExecutionsPage() {
  const { projectId } = useProject();
  return projectId ? <ProjectExecutions key={projectId} projectId={projectId} /> : <p>Sélectionne un projet.</p>;
}

function ProjectExecutions({ projectId }: { projectId: string }) {
  const [items, setItems] = useState<Execution[]>([]);
  const [selected, setSelected] = useState<ExecutionDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const load = useCallback(() => api.enterprise.executions(projectId).then((next) => { setItems(next); setLoaded(true); }), [projectId]);
  useEffect(() => { load().catch((e) => { setError(humanError(e)); setLoaded(true); }); }, [load]);
  const toggleDetail = async (item: Execution) => {
    if (selected?.id === item.id) { setSelected(null); return; }
    setLoadingDetail(item.id);
    setError(null);
    try { setSelected(await api.enterprise.execution(projectId, item.id)); }
    catch (cause) { setError(humanError(cause)); }
    finally { setLoadingDetail(null); }
  };
  return <div className="space-y-8">
    <PageHeader title="Exécutions" description="Chronologie expurgée des conversations : modèle, latence, volume, RAG et statut. Les prompts et réponses complets ne sont pas journalisés." />
    {error ? <Card className="border-error/30 bg-error-soft text-error text-sm">{error}</Card> : null}
    <section><SectionTitle>Historique ({items.length})</SectionTitle>
      {!loaded ? <Skeleton className="h-24" /> : items.length === 0 ? <EmptyState>Aucune exécution. Lance une conversation dans Chat.</EmptyState> : <div className="space-y-3">{items.map((item) => <Card key={item.id} className="space-y-3">
        <div className="flex items-center justify-between gap-3"><span className="font-mono text-sm">{item.id}</span><StatusBadge status={item.status} /></div>
        <div className="flex flex-wrap gap-2"><Pill>{item.model}</Pill>{item.adapter ? <Pill>adapter {item.adapter}</Pill> : null}{item.rag_used ? <Pill>RAG utilisé</Pill> : null}</div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs"><Metric label="Durée" value={item.duration_ms == null ? "—" : `${Math.round(item.duration_ms)} ms`} /><Metric label="Jetons estimés" value={String(item.estimated_tokens ?? "—")} /><Metric label="Entrée" value={`${item.prompt_chars} caractères`} /><Metric label="Sortie" value={`${item.response_chars ?? 0} caractères`} /></div>
        <div className="flex items-center justify-between gap-3 flex-wrap"><p className="text-xs text-text-muted">{new Date(item.started_at).toLocaleString("fr-FR")} · {item.actor_id}</p><div className="flex gap-2"><Button disabled={loadingDetail === item.id} onClick={() => toggleDetail(item)}>{loadingDetail === item.id ? "Chargement…" : selected?.id === item.id ? "Masquer la trace" : "Voir la trace"}</Button><a href={api.enterprise.executionExportUrl(projectId, item.id)} download className="px-3 py-1.5 text-sm rounded-md font-medium bg-accent text-white hover:bg-accent-strong transition-colors">Exporter JSON</a></div></div>
        {selected?.id === item.id ? <Timeline events={selected.events} /> : null}
      </Card>)}</div>}
    </section>
  </div>;
}
function Metric({ label, value }: { label: string; value: string }) { return <div><p className="text-text-muted">{label}</p><p className="text-text-primary font-mono mt-1">{value}</p></div>; }

function Timeline({ events }: { events: TraceEvent[] }) {
  return <div className="border-t border-border pt-4 space-y-0">
    {events.map((event, index) => <div key={`${event.seq}-${event.type}`} className="grid grid-cols-[1rem_1fr] gap-3">
      <div className="flex flex-col items-center"><span className={`mt-1 h-2.5 w-2.5 rounded-full ${event.type.includes("failed") ? "bg-error" : event.type.includes("completed") ? "bg-success" : "bg-accent"}`} />{index < events.length - 1 ? <span className="w-px flex-1 min-h-10 bg-border" /> : null}</div>
      <div className="pb-4"><div className="flex justify-between gap-3 flex-wrap"><p className="text-sm font-medium">{EVENT_LABELS[event.type] || event.type}</p><span className="text-xs font-mono text-text-muted">#{event.seq} · {new Date(event.created_at).toLocaleTimeString("fr-FR")}</span></div><pre className="mt-2 overflow-x-auto rounded-md bg-bg/70 border border-border p-3 text-xs text-text-secondary">{JSON.stringify(event.payload, null, 2)}</pre></div>
    </div>)}
  </div>;
}
