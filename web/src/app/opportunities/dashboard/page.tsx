// web/src/app/opportunities/dashboard/page.tsx
"use client";

import { useEffect, useState } from "react";
import { api, Opportunity, SCORE_LABELS } from "@/lib/api";
import { BarChart } from "@/components/bar-chart";
import { Card, EmptyState, PageHeader } from "@/components/ui";
import { clientsForTarget } from "@/lib/simulator";
import { humanError } from "@/lib/errors";

const MEDALS = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"];

export default function OpportunitiesDashboardPage() {
  const [opportunities, setOpportunities] = useState<Opportunity[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.opportunities.dashboard().then(setOpportunities).catch((e) => setError(humanError(e)));
  }, []);

  if (error) return <Card className="border-error/30 bg-error-soft text-error text-sm">{error}</Card>;
  if (!opportunities) return <p>Chargement…</p>;
  if (opportunities.length === 0) return <EmptyState>Aucune opportunité à comparer.</EmptyState>;

  const clientsFor = (target: number, item: Opportunity) => {
    const result = clientsForTarget(item.monthly_price * 12 + item.setup_price, target);
    return result == null ? "n/a" : result;
  };

  return <div className="space-y-8">
    <PageHeader title="Classement des opportunités" description="Comparaison dynamique des opportunités business IA." />

    <Card>
      <p className="text-xs uppercase tracking-wide text-text-muted mb-3">Score /100</p>
      <BarChart data={opportunities.map((o) => ({ label: o.name, value: o.score.total, highlight: o.score.total >= 85 }))} unit="/100" formatValue={(v) => String(v)} />
    </Card>

    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="text-left text-xs uppercase text-text-muted border-b border-border">
            <th className="py-2 pr-4">Rang</th><th className="py-2 pr-4">Opportunité</th>
            <th className="py-2 pr-4">Score</th><th className="py-2 pr-4">Statut</th>
            <th className="py-2 pr-4">Marge estimée</th><th className="py-2 pr-4">Coût initial</th>
            <th className="py-2 pr-4">Revenu récurrent</th><th className="py-2 pr-4">Difficulté</th>
            <th className="py-2 pr-4">Risque</th>
            <th className="py-2 pr-4">Clients pour 100k€</th><th className="py-2 pr-4">Clients pour 1M€</th>
          </tr>
        </thead>
        <tbody>
          {opportunities.map((item, index) => {
            const label = SCORE_LABELS[item.score.label];
            return <tr key={item.id} className="border-b border-border/60">
              <td className="py-2 pr-4">{MEDALS[index] ?? index + 1}</td>
              <td className="py-2 pr-4 font-medium text-text-primary">{item.name}</td>
              <td className="py-2 pr-4">{label.emoji} {item.score.total}/100</td>
              <td className="py-2 pr-4">{item.status}</td>
              <td className="py-2 pr-4">{item.estimated_margin_pct}%</td>
              <td className="py-2 pr-4">{item.setup_cost.toLocaleString("fr-FR")} €</td>
              <td className="py-2 pr-4">{item.recurring_revenue_potential.toLocaleString("fr-FR")} €</td>
              <td className="py-2 pr-4">dev {item.dev_difficulty}/5 · vente {item.sales_difficulty}/5</td>
              <td className="py-2 pr-4">{item.score.breakdown.risk}/5</td>
              <td className="py-2 pr-4">{clientsFor(100_000, item)}</td>
              <td className="py-2 pr-4">{clientsFor(1_000_000, item)}</td>
            </tr>;
          })}
        </tbody>
      </table>
    </div>
  </div>;
}
