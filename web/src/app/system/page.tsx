"use client";

import { useEffect, useState } from "react";
import { api, SystemHealth } from "@/lib/api";
import { Card, EmptyState, PageHeader, Pill, SectionTitle } from "@/components/ui";

function OkDot({ ok }: { ok: boolean }) {
  return <span className={`inline-block h-2 w-2 rounded-full ${ok ? "bg-success" : "bg-error"}`} />;
}

export default function SystemPage() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = () => {
    api.systemHealth()
      .then((h) => {
        setHealth(h);
        setError(null);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    refresh();
  }, []);

  return (
    <div className="space-y-8">
      <PageHeader
        title="System"
        description="Santé de l'environnement — torch/CUDA, versions figées, GPU, disque, Ollama. Détecte le genre de régression silencieuse qu'un simple pip install peut introduire (ex. torch écrasé par une build CPU-only). Pour gérer les projets (dataset/RAG/modèle isolés), utilise le sélecteur en haut à droite."
      />

      {error && <Card className="border-error/30 bg-error-soft text-error text-sm">{error}</Card>}

      {!health ? (
        <p className="text-text-muted text-sm">{loading ? "Chargement…" : "—"}</p>
      ) : (
        <>
          <Card className={health.ok ? "border-success/30 bg-success-soft" : "border-error/30 bg-error-soft"}>
            <div className="flex items-center gap-2">
              <OkDot ok={health.ok} />
              <span className={`text-sm font-medium ${health.ok ? "text-success" : "text-error"}`}>
                {health.ok ? "Tout est en ordre." : "Problème détecté — voir le détail ci-dessous."}
              </span>
            </div>
          </Card>

          <section>
            <SectionTitle>PyTorch / CUDA</SectionTitle>
            <Card className="space-y-2">
              <Row label="Version torch" value={health.torch_cuda.torch_version ?? "non installé"} ok={!!health.torch_cuda.torch_version} />
              <Row
                label="Build CPU-only"
                value={health.torch_cuda.is_cpu_only_build ? "oui — problème" : "non"}
                ok={!health.torch_cuda.is_cpu_only_build}
              />
              <Row label="CUDA disponible" value={health.torch_cuda.cuda_available ? "oui" : "non"} ok={health.torch_cuda.cuda_available} />
              <Row label="GPU détecté" value={health.torch_cuda.device_name ?? "—"} ok={!!health.torch_cuda.device_name} />
            </Card>
          </section>

          <section>
            <SectionTitle>Versions figées (requirements.txt)</SectionTitle>
            <Card className="p-0 overflow-hidden">
              {health.packages.map((p) => (
                <div key={p.package} className="flex items-center justify-between px-4 py-2.5 border-b border-border last:border-0 text-sm">
                  <div className="flex items-center gap-2">
                    <OkDot ok={p.ok} />
                    <span className="font-mono text-text-primary">{p.package}</span>
                  </div>
                  <div className="text-xs font-mono text-text-muted">
                    {p.installed ?? "non installé"}
                    {p.expected && p.installed !== p.expected && <span className="text-error"> (attendu {p.expected})</span>}
                  </div>
                </div>
              ))}
            </Card>
          </section>

          <div className="grid sm:grid-cols-2 gap-6">
            <section>
              <SectionTitle>GPU</SectionTitle>
              <Card className="space-y-2">
                {health.gpu ? (
                  <>
                    <Row label="Modèle" value={health.gpu.name} ok />
                    <Row
                      label="VRAM"
                      value={`${(health.gpu.memory_used_mb / 1024).toFixed(1)} / ${(health.gpu.memory_total_mb / 1024).toFixed(1)} GB`}
                      ok
                    />
                    <Row label="Utilisation" value={`${health.gpu.utilization_pct}%`} ok />
                  </>
                ) : (
                  <EmptyState>nvidia-smi indisponible.</EmptyState>
                )}
              </Card>
            </section>

            <section>
              <SectionTitle>Disque</SectionTitle>
              <Card className="space-y-2">
                <Row label="Libre" value={`${health.disk.free_gb} GB`} ok={health.disk.free_gb > 5} />
                <Row label="Total" value={`${health.disk.total_gb} GB`} ok />
              </Card>
            </section>
          </div>

          <section>
            <SectionTitle>Ollama</SectionTitle>
            <Card className="space-y-2">
              <Row label="Statut" value={health.ollama.running ? "en cours" : "arrêté"} ok={health.ollama.running} />
              {health.ollama.models.length > 0 && (
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {health.ollama.models.map((m) => (
                    <Pill key={m}>{m}</Pill>
                  ))}
                </div>
              )}
            </Card>
          </section>
        </>
      )}
    </div>
  );
}

function Row({ label, value, ok }: { label: string; value: string; ok: boolean }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-text-secondary">{label}</span>
      <span className="flex items-center gap-2">
        <span className="font-mono text-text-primary">{value}</span>
        <OkDot ok={ok} />
      </span>
    </div>
  );
}
