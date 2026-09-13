"use client";

import { useCallback, useEffect, useState } from "react";
import { api, Provider } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import { Button, Card, EmptyState, Input, PageHeader, Pill, SectionTitle } from "@/components/ui";

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
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => api.enterprise.providers(projectId).then(setItems), [projectId]);
  useEffect(() => { Promise.resolve().then(load).catch((e) => setMessage(String(e))); }, [load]);
  const act = async (work: () => Promise<unknown>) => { setBusy(true); setMessage(null); try { await work(); await load(); } catch (e) { setMessage(String(e)); } finally { setBusy(false); } };
  return <div className="space-y-8">
    <PageHeader title="Fournisseurs" description="Configure les moteurs utilisés par les agents. Les secrets restent dans les variables d’environnement du serveur." />
    {message ? <Card className="text-sm">{message}</Card> : null}
    <section><SectionTitle>Ajouter ou mettre à jour</SectionTitle><Card className="grid gap-3 md:grid-cols-2">
      <label className="text-xs text-text-muted">Nom<Input value={name} onChange={setName} className="w-full mt-1" /></label>
      <label className="text-xs text-text-muted">Type<select value={type} onChange={(e) => { const next=e.target.value as Provider["type"]; setType(next); if(next === "ollama") setUrl("http://localhost:11434"); }} className="w-full mt-1 bg-bg border border-border rounded-md px-3 py-1.5 text-sm"><option value="ollama">Ollama</option><option value="openai-compatible">API compatible OpenAI</option><option value="anthropic-compatible">API compatible Anthropic</option></select></label>
      <label className="text-xs text-text-muted">URL de base<Input value={url} onChange={setUrl} className="w-full mt-1 font-mono" /></label>
      <label className="text-xs text-text-muted">Modèle<Input value={model} onChange={setModel} placeholder="llama3.2:3b" className="w-full mt-1 font-mono" /></label>
      <label className="text-xs text-text-muted md:col-span-2">Variable contenant la clé API<Input value={secretEnv} onChange={setSecretEnv} placeholder="PROVIDER_API_KEY — vide pour Ollama" className="w-full mt-1 font-mono" /></label>
      <div className="md:col-span-2"><Button variant="accent" disabled={busy || !name.trim() || !url.trim() || !model.trim()} onClick={() => act(() => api.enterprise.updateProvider(projectId, { name: name.trim(), type, base_url: url.trim(), model: model.trim(), api_key_env: secretEnv.trim() || null, enabled: true }))}>Enregistrer</Button></div>
    </Card></section>
    <section><SectionTitle>Fournisseurs configurés ({items.length})</SectionTitle>{items.length === 0 ? <EmptyState>Aucun fournisseur.</EmptyState> : <div className="space-y-3">{items.map((item) => <Card key={item.id} className="flex items-center justify-between gap-4 flex-wrap"><div><div className="flex gap-2"><span className="font-medium text-sm">{item.name}</span><Pill>{item.type}</Pill></div><p className="text-xs text-text-muted mt-2 font-mono">{item.base_url} · {item.model}</p><p className="text-xs text-text-muted mt-1">Secret : {item.api_key_env || "aucun"}</p></div><div className="flex gap-2"><Button disabled={busy} onClick={() => act(async () => { const result=await api.enterprise.testProvider(projectId,item.id); setMessage(`Connexion réussie en ${result.latency_ms} ms`); })}>Tester</Button><Button variant="danger" disabled={busy} onClick={() => confirm(`Supprimer ${item.name} ?`) && act(() => api.enterprise.removeProvider(projectId,item.id))}>Supprimer</Button></div></Card>)}</div>}</section>
  </div>;
}
