// web/src/app/opportunities/page.tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, Opportunity, SCORE_LABELS } from "@/lib/api";
import { Button, Card, EmptyState, Input, PageHeader, StatusBadge } from "@/components/ui";

export default function OpportunitiesPage() {
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setOpportunities(await api.opportunities.list());
  }, []);

  useEffect(() => {
    let active = true;

    refresh().then(() => {
      if (active) {
        // empty
      }
    });

    return () => {
      active = false;
    };
  }, [refresh]);

  const create = async () => {
    setError(null);
    setBusy(true);
    try {
      await api.opportunities.create({ name: name.trim() });
      setName("");
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return <div className="space-y-6">
    <PageHeader title="Opportunités" description="Découvrez les opportunités IA pour l'ESN." />
    {error && <Card className="border-error/30 bg-error-soft text-error text-sm">{error}</Card>}
    <Card className="flex flex-wrap gap-2">
      <Input value={name} onChange={setName} placeholder="Nom de la nouvelle opportunité" className="flex-1 min-w-56" />
      <Button variant="accent" disabled={busy || !name.trim()} onClick={create}>Créer</Button>
    </Card>
    {opportunities.length === 0 ? <EmptyState>Aucune opportunité pour l'instant.</EmptyState> : <div className="grid gap-3 md:grid-cols-2">
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
