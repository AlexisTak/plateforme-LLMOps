"use client";

import { useEffect, useState } from "react";
import { api, type OfflineStatus } from "@/lib/api";
import { useAction } from "@/lib/use-action";

const ON_HELP =
  "Mode hors ligne actif : l’API refuse tout appel sortant (fournisseurs IA externes, MCP, outils) " +
  "sauf Ollama local, et HuggingFace est coupé. Les données ne quittent pas cette machine.";
const OFF_HELP =
  "Activer pour garantir que rien ne sort de la machine (RAG et chat sur données sensibles). " +
  "Les modèles doivent déjà être téléchargés.";

// Sidebar switch for the platform-wide offline mode (admin only, see api/outbound.py).
export function OfflineToggle() {
  const [status, setStatus] = useState<OfflineStatus | null>(null);
  const toggle = useAction((enabled: boolean) => api.offline.set(enabled), {
    success: (s) => (s.enabled ? "Mode hors ligne activé — aucun appel sortant" : "Mode hors ligne désactivé"),
  });

  useEffect(() => {
    const check = () => api.offline.get().then(setStatus).catch(() => setStatus(null));
    check();
    const interval = setInterval(check, 15000);
    return () => clearInterval(interval);
  }, []);

  if (status === null) return null;

  const { enabled, locked } = status;
  const onClick = async () => {
    const result = await toggle.run(!enabled);
    if (result) setStatus(result);
  };

  return (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      onClick={onClick}
      disabled={toggle.busy || locked}
      title={locked ? `${ON_HELP} Imposé par BISCUITS_OFFLINE dans le .env du serveur.` : enabled ? ON_HELP : OFF_HELP}
      className={`mt-2 w-full flex items-center justify-between gap-2 px-3 py-2 rounded-md border text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg disabled:cursor-not-allowed ${
        enabled
          ? "border-success/40 bg-success-soft text-success"
          : "border-border text-text-secondary hover:text-text-primary hover:bg-surface-hover"
      }`}
    >
      <span className="flex flex-col items-start leading-tight">
        <span>Mode hors ligne</span>
        <span className={`text-[10px] ${enabled ? "text-success/80" : "text-text-muted"}`}>
          {locked ? "Imposé par .env" : enabled ? "Rien ne sort de la machine" : "Appels externes autorisés"}
        </span>
      </span>
      <span
        aria-hidden
        className={`relative inline-flex h-4 w-7 shrink-0 rounded-full transition-colors ${enabled ? "bg-success" : "bg-surface-hover ring-1 ring-border"}`}
      >
        <span
          className={`absolute top-0.5 h-3 w-3 rounded-full bg-white transition-transform ${enabled ? "translate-x-3.5" : "translate-x-0.5"}`}
        />
      </span>
    </button>
  );
}
