// web/src/app/opportunities/page.tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, Opportunity, SCORE_LABELS } from "@/lib/api";
import { Button, Card, EmptyState, Input, PageHeader, Skeleton, StatusBadge } from "@/components/ui";
import { useAction } from "@/lib/use-action";

export default function OpportunitiesPage() {
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [name, setName] = useState("");
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(async () => {
    const next = await api.opportunities.list();
    setOpportunities(next);
    setLoaded(true);
  }, []);

  useEffect(() => {
    Promise.resolve().then(refresh).catch(() => setLoaded(true));
  }, [refresh]);

  const createAction = useAction((name: string) => api.opportunities.create({ name }), {
    success: (item) => `${item.name} créée.`,
  });
  const create = async () => {
    const created = await createAction.run(name.trim());
    if (created) {
      setName("");
      await refresh();
    }
  };

  return <div className="space-y-6">
    <PageHeader title="Opportunités Business IA" description="Cataloguer, scorer et suivre les offres IA."
      action={<Link href="/opportunities/dashboard" className="px-3 py-1.5 text-sm rounded-md bg-surface-hover text-text-primary border border-border">Voir le dashboard</Link>} />
    {createAction.error ? <Card className="border-error/30 bg-error-soft text-error text-sm">{createAction.error}</Card> : null}
    <Card className="flex flex-wrap gap-2">
      <Input value={name} onChange={setName} placeholder="Nom de la nouvelle opportunité" className="flex-1 min-w-56" />
      <Button variant="accent" disabled={createAction.busy || !name.trim()} onClick={create}>Créer</Button>
    </Card>
    {!loaded ? <div className="grid gap-3 md:grid-cols-2"><Skeleton className="h-28" /><Skeleton className="h-28" /></div> : opportunities.length === 0 ? <EmptyState>Aucune opportunité pour l&apos;instant.</EmptyState> : <div className="grid gap-3 md:grid-cols-2">
      {opportunities.map((item) => {
        const label = SCORE_LABELS[item.score.label];
        return <Link key={item.id} href={`/opportunities/${item.id}`}>
          <Card className="h-full hover:border-border-strong transition-colors">
            <div className="flex items-center justify-between gap-2">
              <p className="font-medium text-text-primary">{item.name}</p>
              <StatusBadge status={item.status} />
            </div>
            <p className="text-xs text-text-muted mt-1">{item.sector || "Secteur non renseigné"}</p>
            <p className="text-sm mt-3">{label.emoji} {label.text} · <span className="font-mono">{item.score.total}/100</span></p>
          </Card>
        </Link>;
      })}
    </div>}
  </div>;
}
