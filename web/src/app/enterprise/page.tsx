"use client";

import { useCallback, useEffect, useState } from "react";
import { api, AuditEvent, EnterpriseContext, EnterpriseMetrics, ModelVersion, ProjectMember, ProjectQuota } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import { Button, Card, EmptyState, Input, PageHeader, Pill, Select, SectionTitle, Skeleton, StatusBadge } from "@/components/ui";
import { humanError } from "@/lib/errors";

const NEXT: Record<ModelVersion["status"], ModelVersion["status"] | null> = {
  draft: "evaluated", evaluated: "approved", approved: "production", production: "archived", archived: "production",
};

export default function EnterprisePage() {
  const { projectId } = useProject();
  return projectId ? <ProjectEnterprise key={projectId} projectId={projectId} /> : <p>Sélectionne un projet.</p>;
}

function ProjectEnterprise({ projectId }: { projectId: string }) {
  const [context, setContext] = useState<EnterpriseContext | null>(null);
  const [metrics, setMetrics] = useState<EnterpriseMetrics | null>(null);
  const [versions, setVersions] = useState<ModelVersion[]>([]);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [quota, setQuota] = useState<ProjectQuota | null>(null);
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [version, setVersion] = useState("");
  const [notes, setNotes] = useState("");
  const [memberEmail, setMemberEmail] = useState("");
  const [memberName, setMemberName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(async () => {
    const [c, m, v, a, q, team] = await Promise.all([
      api.enterprise.context(), api.enterprise.metrics(), api.enterprise.registry(projectId),
      api.enterprise.audit(projectId), api.enterprise.quota(projectId), api.enterprise.members(projectId),
    ]);
    setContext(c); setMetrics(m); setVersions(v); setEvents(a); setQuota(q); setMembers(team); setError(null);
    setLoaded(true);
  }, [projectId]);

  useEffect(() => {
    let active = true;
    Promise.resolve().then(refresh).catch((e) => { if (active) setError(humanError(e)); });
    return () => { active = false; };
  }, [refresh]);

  const act = async (work: () => Promise<unknown>) => {
    setBusy(true); setError(null);
    try { await work(); await refresh(); } catch (e) { setError(humanError(e)); } finally { setBusy(false); }
  };

  return <div className="space-y-10">
    <PageHeader title="Entreprise" description="Identité, registre de modèles, approbations, quotas, audit et observabilité — centralisés sans surcharger les pages métier." action={<Button onClick={() => refresh()} disabled={busy}>Actualiser</Button>} />
    {error ? <Card className="border-error/30 bg-error-soft text-error text-sm">{error}</Card> : null}

    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {!loaded ? <><Skeleton className="h-20" /><Skeleton className="h-20" /><Skeleton className="h-20" /><Skeleton className="h-20" /></> : <>
        <Metric label="Identité" value={context ? `${context.actor.name} · ${context.actor.role}` : "…"} />
        <Metric label="Authentification" value={context?.auth_mode === "proxy" ? "SSO via proxy" : "Mode local"} />
        <Metric label="Requêtes · p95" value={metrics ? `${metrics.requests_total ?? 0} · ${metrics.latency_p95_ms} ms` : "…"} />
        <Metric label="Jobs" value={metrics ? `${metrics.jobs_running} actif · ${metrics.jobs_failed} échoué` : "…"} />
      </>}
    </div>

    <section>
      <SectionTitle>Équipe et portabilité</SectionTitle>
      <Card className="mb-3 flex flex-wrap gap-2">
        <Input value={memberName} onChange={setMemberName} placeholder="Nom" className="min-w-40" />
        <Input value={memberEmail} onChange={setMemberEmail} placeholder="E-mail professionnel" className="flex-1 min-w-56" />
        <Button disabled={busy || !memberEmail.trim() || !memberName.trim()} onClick={() => act(async () => {
          const email = memberEmail.trim();
          await api.enterprise.updateMember(projectId, { actor_id: email.toLowerCase(), email, name: memberName.trim(), role: "viewer" });
          setMemberEmail(""); setMemberName("");
        })}>Ajouter comme viewer</Button>
        <a href={api.enterprise.backupUrl(projectId)} className="px-3 py-1.5 text-sm rounded-md bg-surface-hover text-text-primary border border-border">Télécharger la sauvegarde</a>
      </Card>
      <div className="grid gap-2 md:grid-cols-2">{members.map((member) => <Card key={member.actor_id} className="flex items-center justify-between gap-3">
        <div><p className="text-sm text-text-primary">{member.name}</p><p className="text-xs text-text-muted">{member.email}</p></div>
        <Select value={member.role} disabled={busy} className="text-xs" onChange={(v) => act(() => api.enterprise.updateMember(projectId, { actor_id: member.actor_id, email: member.email, name: member.name, role: v as ProjectMember["role"] }))}>
          {(["viewer", "operator", "reviewer", "admin"] as const).map((role) => <option key={role}>{role}</option>)}
        </Select>
      </Card>)}</div>
    </section>

    <section>
      <SectionTitle>Registre et validation</SectionTitle>
      <Card className="mb-3 flex flex-wrap gap-2">
        <Input value={version} onChange={setVersion} placeholder="Version, ex. 1.0.0" className="min-w-48" />
        <Input value={notes} onChange={setNotes} placeholder="Notes de livraison" className="flex-1 min-w-56" />
        <Button variant="accent" disabled={busy || !version.trim()} onClick={() => act(async () => { await api.enterprise.createVersion(projectId, version.trim(), notes.trim()); setVersion(""); setNotes(""); })}>Créer l’instantané</Button>
      </Card>
      {versions.length === 0 ? <EmptyState>Aucune version enregistrée.</EmptyState> : <div className="space-y-2">{versions.map((item) => <Card key={item.id} className="flex items-center justify-between gap-4 flex-wrap">
        <div><div className="flex items-center gap-2"><span className="font-mono text-sm">v{item.version}</span><StatusBadge status={item.status} /></div><p className="text-xs text-text-muted mt-1">{item.model} · dataset {item.dataset_version || "non versionné"} · benchmark {item.benchmark_generated_at ? "présent" : "absent"}</p>{item.notes ? <p className="text-sm text-text-secondary mt-2">{item.notes}</p> : null}</div>
        {NEXT[item.status] ? <Button disabled={busy} onClick={() => act(() => api.enterprise.transition(projectId, item.id, NEXT[item.status]!))}>{item.status === "archived" ? "Rollback en production" : `Passer à « ${NEXT[item.status]} »`}</Button> : null}
      </Card>)}</div>}
    </section>

    <section>
      <SectionTitle>Capacité et quotas</SectionTitle>
      {quota ? <Card className="grid gap-4 sm:grid-cols-4 items-end">
        <QuotaInput label="Jobs simultanés" value={quota.max_concurrent_jobs} onChange={(v) => setQuota({ ...quota, max_concurrent_jobs: v })} />
        <QuotaInput label="Jobs par jour" value={quota.max_daily_jobs} onChange={(v) => setQuota({ ...quota, max_daily_jobs: v })} />
        <QuotaInput label="Stockage (Go)" value={quota.max_storage_gb} onChange={(v) => setQuota({ ...quota, max_storage_gb: v })} />
        <Button disabled={busy} onClick={() => act(() => api.enterprise.updateQuota(projectId, quota))}>Enregistrer</Button>
        <p className="text-xs text-text-muted sm:col-span-4">{quota.running_jobs ?? 0} job(s) actif(s) · {quota.storage_used_gb ?? 0} Go utilisés. Les trois limites sont appliquées avant l’exécution.</p>
      </Card> : <EmptyState>Chargement des quotas…</EmptyState>}
    </section>

    <section>
      <SectionTitle>Journal d’audit</SectionTitle>
      <Card className="mb-3 flex items-center justify-between text-sm"><span>Chaîne d’intégrité</span><Pill>{context?.audit_chain_valid ? "valide" : "invalide"}</Pill></Card>
      {events.length === 0 ? <EmptyState>Aucun événement pour ce projet.</EmptyState> : <div className="space-y-2">{events.slice(0, 30).map((event) => <Card key={event.id} className="py-3">
        <div className="flex justify-between gap-3 text-sm"><span className="font-mono">{event.action}</span><time className="text-text-muted text-xs">{new Date(event.created_at).toLocaleString("fr-FR")}</time></div>
        <p className="text-xs text-text-muted mt-1">{event.actor_id} · {event.resource_id} · empreinte {event.event_hash.slice(0, 12)}</p>
      </Card>)}</div>}
    </section>
  </div>;
}

function Metric({ label, value }: { label: string; value: string }) { return <Card><p className="text-xs uppercase tracking-wide text-text-muted">{label}</p><p className="text-sm font-medium mt-2">{value}</p></Card>; }
function QuotaInput({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) { return <label className="text-xs text-text-muted">{label}<input type="number" min="1" value={value} onChange={(e) => onChange(Number(e.target.value))} className="mt-1 w-full bg-bg border border-border rounded-md px-3 py-1.5 text-sm text-text-primary" /></label>; }
