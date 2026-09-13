"use client";

import { useCallback, useEffect, useState } from "react";
import { api, Execution } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import { Card, EmptyState, PageHeader, Pill, SectionTitle, StatusBadge } from "@/components/ui";

export default function ExecutionsPage() {
  const { projectId } = useProject();
  return projectId ? <ProjectExecutions key={projectId} projectId={projectId} /> : <p>Sélectionne un projet.</p>;
}

function ProjectExecutions({ projectId }: { projectId: string }) {
  const [items, setItems] = useState<Execution[]>([]);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => api.enterprise.executions(projectId).then(setItems), [projectId]);
  useEffect(() => { Promise.resolve().then(load).catch((e) => setError(String(e))); }, [load]);
  return <div className="space-y-8">
    <PageHeader title="Exécutions" description="Chronologie expurgée des conversations : modèle, latence, volume, RAG et statut. Les prompts et réponses complets ne sont pas journalisés." />
    {error ? <Card className="border-error/30 bg-error-soft text-error text-sm">{error}</Card> : null}
    <section><SectionTitle>Historique ({items.length})</SectionTitle>
      {items.length === 0 ? <EmptyState>Aucune exécution. Lance une conversation dans Chat.</EmptyState> : <div className="space-y-3">{items.map((item) => <Card key={item.id} className="space-y-3">
        <div className="flex items-center justify-between gap-3"><span className="font-mono text-sm">{item.id}</span><StatusBadge status={item.status} /></div>
        <div className="flex flex-wrap gap-2"><Pill>{item.model}</Pill>{item.adapter ? <Pill>adapter {item.adapter}</Pill> : null}{item.rag_used ? <Pill>RAG utilisé</Pill> : null}</div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs"><Metric label="Durée" value={item.duration_ms == null ? "—" : `${Math.round(item.duration_ms)} ms`} /><Metric label="Jetons estimés" value={String(item.estimated_tokens ?? "—")} /><Metric label="Entrée" value={`${item.prompt_chars} caractères`} /><Metric label="Sortie" value={`${item.response_chars ?? 0} caractères`} /></div>
        <p className="text-xs text-text-muted">{new Date(item.started_at).toLocaleString("fr-FR")} · {item.actor_id}</p>
      </Card>)}</div>}
    </section>
  </div>;
}
function Metric({ label, value }: { label: string; value: string }) { return <div><p className="text-text-muted">{label}</p><p className="text-text-primary font-mono mt-1">{value}</p></div>; }
