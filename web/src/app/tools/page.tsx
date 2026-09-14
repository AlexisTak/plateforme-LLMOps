"use client";

import { useCallback, useEffect, useState } from "react";
import { Approval, api, McpServer, ToolDefinition, ToolPolicy } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import { Button, Card, EmptyState, Input, PageHeader, Pill, Select, SectionTitle, Skeleton, StatusBadge } from "@/components/ui";

export default function ToolsPage() {
  const { projectId } = useProject();
  return projectId ? <ProjectTools key={projectId} projectId={projectId} /> : <p>Sélectionne un projet.</p>;
}

function ProjectTools({ projectId }: { projectId: string }) {
  const [tools, setTools] = useState<ToolDefinition[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [policies, setPolicies] = useState<ToolPolicy[]>([]);
  const [mcpServers, setMcpServers] = useState<McpServer[]>([]);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [method, setMethod] = useState<"GET" | "POST">("GET");
  const [approval, setApproval] = useState(false);
  const [policyName, setPolicyName] = useState("");
  const [effect, setEffect] = useState<ToolPolicy["effect"]>("require_approval");
  const [targetTool, setTargetTool] = useState("");
  const [priority, setPriority] = useState("100");
  const [mcpName, setMcpName] = useState("");
  const [mcpUrl, setMcpUrl] = useState("");
  const [mcpKeyEnv, setMcpKeyEnv] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(() => Promise.all([
    api.enterprise.tools(projectId),
    api.enterprise.approvals(projectId).catch(() => []),
    api.enterprise.toolPolicies(projectId),
    api.enterprise.mcpServers(projectId),
  ]).then(([toolItems, approvalItems, policyItems, serverItems]) => {
    setTools(toolItems);
    setApprovals(approvalItems);
    setPolicies(policyItems);
    setMcpServers(serverItems);
    setLoaded(true);
  }), [projectId]);

  useEffect(() => {
    Promise.resolve().then(load).catch((error) => { setMessage(String(error)); setLoaded(true); });
  }, [load]);

  const act = async (work: () => Promise<unknown>) => {
    setBusy(true);
    setMessage(null);
    try {
      const result = await work();
      setMessage(JSON.stringify(result));
      await load();
    } catch (error) {
      setMessage(String(error));
    } finally {
      setBusy(false);
    }
  };

  return <div className="space-y-8">
    <PageHeader title="Outils, politiques et approbations" description="Catalogue HTTP et règles d’exécution déclaratives. Une règle deny est toujours prioritaire." />
    {message ? <Card className="text-xs font-mono break-all">{message}</Card> : null}

    <section>
      <SectionTitle>Serveurs MCP en lecture</SectionTitle>
      <Card className="grid gap-3 md:grid-cols-2 lg:grid-cols-4 mb-3">
        <Input value={mcpName} onChange={setMcpName} placeholder="Nom du serveur" />
        <Input value={mcpUrl} onChange={setMcpUrl} placeholder="https://service.example/mcp" />
        <Input value={mcpKeyEnv} onChange={setMcpKeyEnv} placeholder="MCP_API_KEY (facultatif)" />
        <Button variant="accent" disabled={busy || !mcpName || !mcpUrl} onClick={() => act(() => api.enterprise.updateMcpServer(projectId, { name: mcpName, url: mcpUrl, api_key_env: mcpKeyEnv || null, enabled: true }))}>Enregistrer le serveur</Button>
      </Card>
      {!loaded ? <Skeleton className="h-16" /> : mcpServers.length === 0 ? <EmptyState>Aucun serveur MCP.</EmptyState> : <div className="space-y-2">{mcpServers.map((server) => <Card key={server.id} className="flex justify-between gap-3 flex-wrap">
        <div><p className="text-sm font-medium">{server.name}</p><p className="text-xs font-mono text-text-muted mt-1">{server.url}</p>{server.api_key_env ? <div className="mt-2"><Pill>secret: {server.api_key_env}</Pill></div> : null}</div>
        <Button disabled={busy} onClick={() => act(() => api.enterprise.syncMcpServer(projectId, server.id))}>Synchroniser les outils en lecture</Button>
      </Card>)}</div>}
    </section>

    <section>
      <SectionTitle>Déclarer un outil</SectionTitle>
      <Card className="grid gap-3 md:grid-cols-2">
        <Input value={name} onChange={setName} placeholder="Nom de l’outil" />
        <Input value={url} onChange={setUrl} placeholder="https://service/api/action" />
        <Select value={method} onChange={(v) => setMethod(v as "GET" | "POST")}>
          <option>GET</option><option>POST</option>
        </Select>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={approval} onChange={(event) => setApproval(event.target.checked)} />Approbation par défaut</label>
        <Button variant="accent" disabled={busy || !name || !url} onClick={() => act(() => api.enterprise.updateTool(projectId, { name, method, url, approval_required: approval, timeout_seconds: 5, max_response_bytes: 100000 }))}>Enregistrer</Button>
      </Card>
    </section>

    <section>
      <SectionTitle>Politiques ({policies.length})</SectionTitle>
      <Card className="grid gap-3 md:grid-cols-2 lg:grid-cols-5 mb-3">
        <Input value={policyName} onChange={setPolicyName} placeholder="Nom de la règle" />
        <Select value={effect} onChange={(v) => setEffect(v as ToolPolicy["effect"])}>
          <option value="allow">Autoriser</option><option value="require_approval">Exiger une approbation</option><option value="deny">Refuser</option>
        </Select>
        <Select value={targetTool} onChange={setTargetTool}>
          <option value="">Tous les outils</option>{tools.map((tool) => <option key={tool.id} value={tool.id}>{tool.name}</option>)}
        </Select>
        <Input value={priority} onChange={setPriority} placeholder="Priorité" />
        <Button variant="accent" disabled={busy || !policyName || !Number.isInteger(Number(priority))} onClick={() => act(() => api.enterprise.updateToolPolicy(projectId, { name: policyName, effect, tool_id: targetTool || null, priority: Number(priority), enabled: true }))}>Enregistrer la règle</Button>
      </Card>
      {!loaded ? <Skeleton className="h-16" /> : policies.length === 0 ? <EmptyState>Aucune politique : la configuration par défaut des outils s’applique.</EmptyState> : <div className="space-y-2">{policies.map((policy) => <Card key={policy.id} className="flex justify-between gap-3 flex-wrap">
        <div><p className="text-sm font-medium">{policy.name}</p><div className="flex gap-2 mt-2"><Pill>{policy.effect}</Pill><Pill>{policy.tool_name || "tous les outils"}</Pill><Pill>priorité {policy.priority}</Pill></div></div>
        <Button variant="danger" disabled={busy} onClick={() => act(() => api.enterprise.removeToolPolicy(projectId, policy.id))}>Supprimer</Button>
      </Card>)}</div>}
    </section>

    <section>
      <SectionTitle>Catalogue ({tools.length})</SectionTitle>
      {!loaded ? <Skeleton className="h-16" /> : tools.length === 0 ? <EmptyState>Aucun outil.</EmptyState> : <div className="space-y-2">{tools.map((tool) => <Card key={tool.id} className="flex justify-between gap-3 flex-wrap">
        <div><p className="text-sm font-medium">{tool.name}</p><p className="text-xs font-mono text-text-muted mt-1">{tool.method} {tool.action || tool.url}</p>{tool.description ? <p className="text-xs text-text-secondary mt-1 max-w-xl">{tool.description}</p> : null}<div className="flex gap-2 mt-2">{tool.connector_type === "mcp" ? <Pill>MCP lecture</Pill> : null}{tool.approval_required ? <Pill>approbation par défaut</Pill> : <Pill>exécution directe par défaut</Pill>}</div></div>
        <Button disabled={busy} onClick={() => act(() => api.enterprise.executeTool(projectId, tool.id, {}))}>Tester sans arguments</Button>
      </Card>)}</div>}
    </section>

    <section>
      <SectionTitle>Demandes d’approbation</SectionTitle>
      {!loaded ? <Skeleton className="h-16" /> : approvals.length === 0 ? <EmptyState>Aucune demande.</EmptyState> : <div className="space-y-2">{approvals.map((item) => <Card key={item.id} className="flex justify-between gap-3 flex-wrap">
        <div><div className="flex gap-2"><span className="text-sm font-medium">{item.tool_name}</span><StatusBadge status={item.status} /></div><p className="text-xs text-text-muted mt-1">Demandé par {item.requester_id}</p></div>
        {item.status === "pending" ? <div className="flex gap-2"><Button disabled={busy} variant="danger" onClick={() => act(() => api.enterprise.decideApproval(projectId, item.id, "denied"))}>Refuser</Button><Button disabled={busy} variant="accent" onClick={() => act(() => api.enterprise.decideApproval(projectId, item.id, "approved"))}>Approuver et exécuter</Button></div> : null}
      </Card>)}</div>}
    </section>
  </div>;
}
