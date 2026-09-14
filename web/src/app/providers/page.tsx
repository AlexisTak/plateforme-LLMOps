"use client";

import { useCallback, useEffect, useState } from "react";
import { api, Provider } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import { Button, Card, ConfirmDialog, EmptyState, Input, PageHeader, Pill, Select, SectionTitle, Skeleton } from "@/components/ui";
import { useAction } from "@/lib/use-action";

export default function ProvidersPage() {
  const { projectId } = useProject();
  return projectId ? <ProjectProviders key={projectId} projectId={projectId} /> : <p>Sélectionne un projet.</p>;
}

function ProjectProviders({ projectId }: { projectId: string }) {
  const [items, setItems] = useState<Provider[]>([]);
  const [name, setName] = useState("Ollama local");
  const [type, setType] = useState<Provider["type"]>("ollama");
  const [url, setUrl] = useState("http://localhost:11434");
  const [model, setModel] = useState("");
  const [secretEnv, setSecretEnv] = useState("");
  const [loaded, setLoaded] = useState(false);
  const load = useCallback(() => api.enterprise.providers(projectId).then((next) => { setItems(next); setLoaded(true); }), [projectId]);
  useEffect(() => { load().catch(() => setLoaded(true)); }, [load]);

  const saveAction = useAction(
    (params: Parameters<typeof api.enterprise.updateProvider>[1]) => api.enterprise.updateProvider(projectId, params),
    { success: "Fournisseur enregistré." },
  );
  const testAction = useAction((id: string) => api.enterprise.testProvider(projectId, id), {
    success: (result) => `Connexion réussie en ${result.latency_ms} ms`,
  });
  const [pendingRemove, setPendingRemove] = useState<Provider | null>(null);
  const removeAction = useAction((id: string) => api.enterprise.removeProvider(projectId, id), { success: "Fournisseur supprimé." });
  const confirmRemove = async () => {
    if (!pendingRemove) return;
    const item = pendingRemove;
    setPendingRemove(null);
    const res = await removeAction.run(item.id);
    if (res) load();
  };

  const busy = saveAction.busy || testAction.busy || removeAction.busy;

  return <div className="space-y-8">
    <PageHeader title="Fournisseurs" description="Configure les moteurs utilisés par les agents. Les secrets restent dans les variables d’environnement du serveur." />
    <ConfirmDialog
      open={!!pendingRemove}
      title="Supprimer ce fournisseur ?"
      description={pendingRemove?.name}
      confirmLabel="Supprimer"
      danger
      onConfirm={confirmRemove}
      onCancel={() => setPendingRemove(null)}
    />
    <section><SectionTitle>Ajouter ou mettre à jour</SectionTitle><Card className="grid gap-3 md:grid-cols-2">
      <label className="text-xs text-text-muted">Nom<Input value={name} onChange={setName} className="w-full mt-1" /></label>
      <label className="text-xs text-text-muted">Type<Select value={type} onChange={(v) => { const next = v as Provider["type"]; setType(next); if (next === "ollama") setUrl("http://localhost:11434"); }} className="w-full mt-1"><option value="ollama">Ollama</option><option value="openai-compatible">API compatible OpenAI</option><option value="anthropic-compatible">API compatible Anthropic</option></Select></label>
      <label className="text-xs text-text-muted">URL de base<Input value={url} onChange={setUrl} className="w-full mt-1 font-mono" /></label>
      <label className="text-xs text-text-muted">Modèle<Input value={model} onChange={setModel} placeholder="llama3.2:3b" className="w-full mt-1 font-mono" /></label>
      <label className="text-xs text-text-muted md:col-span-2">Variable contenant la clé API<Input value={secretEnv} onChange={setSecretEnv} placeholder="PROVIDER_API_KEY — vide pour Ollama" className="w-full mt-1 font-mono" /></label>
      <div className="md:col-span-2"><Button variant="accent" disabled={busy || !name.trim() || !url.trim() || !model.trim()} onClick={() => saveAction.run({ name: name.trim(), type, base_url: url.trim(), model: model.trim(), api_key_env: secretEnv.trim() || null, enabled: true }).then((r) => r && load())}>Enregistrer</Button></div>
    </Card></section>
    <section><SectionTitle>Fournisseurs configurés ({items.length})</SectionTitle>
      {!loaded ? <Skeleton className="h-20" /> : items.length === 0 ? <EmptyState>Aucun fournisseur.</EmptyState> : <div className="space-y-3">{items.map((item) => <Card key={item.id} className="flex items-center justify-between gap-4 flex-wrap"><div><div className="flex gap-2"><span className="font-medium text-sm">{item.name}</span><Pill>{item.type}</Pill></div><p className="text-xs text-text-muted mt-2 font-mono">{item.base_url} · {item.model}</p><p className="text-xs text-text-muted mt-1">Secret : {item.api_key_env || "aucun"}</p></div><div className="flex gap-2"><Button disabled={busy} onClick={() => testAction.run(item.id)}>Tester</Button><Button variant="danger" disabled={busy} onClick={() => setPendingRemove(item)}>Supprimer</Button></div></Card>)}</div>}
    </section>
  </div>;
}
