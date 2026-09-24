"use client";

import { useCallback, useEffect, useState } from "react";
import { AgentBudget, api, AuditEvent, EnterpriseContext, EnterpriseMetrics, ModelVersion, ProjectMember, ProjectQuota, type RoleName, type User } from "@/lib/api";
import { ROLE_LABELS } from "@/lib/auth-context";
import { useProject } from "@/lib/project-context";
import { Button, Card, EmptyState, Input, PageHeader, Pill, Select, SectionTitle, Skeleton, StatusBadge } from "@/components/ui";
import { humanError } from "@/lib/errors";

const ROLE_NAMES: RoleName[] = ["viewer", "operator", "reviewer", "admin"];
const AUTH_MODE_LABELS: Record<EnterpriseContext["auth_mode"], string> = {
  local: "Mode local (sans compte)", login: "Comptes locaux", proxy: "SSO via proxy",
};

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
  const [budget, setBudget] = useState<AgentBudget | null>(null);
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [version, setVersion] = useState("");
  const [notes, setNotes] = useState("");
  const [memberEmail, setMemberEmail] = useState("");
  const [memberName, setMemberName] = useState("");
  const [candidates, setCandidates] = useState<Pick<User, "id" | "email" | "name">[]>([]);
  const [candidateId, setCandidateId] = useState("");
  const [candidateRole, setCandidateRole] = useState<RoleName>("viewer");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(async () => {
    const [c, m, v, a, q, b, team, accounts] = await Promise.all([
      api.enterprise.context(), api.enterprise.metrics(), api.enterprise.registry(projectId),
      api.enterprise.audit(projectId), api.enterprise.quota(projectId), api.enterprise.budget(projectId), api.enterprise.members(projectId),
      // project admins only (403 otherwise): no picker for the others
      api.enterprise.memberCandidates(projectId).catch(() => []),
    ]);
    setContext(c); setMetrics(m); setVersions(v); setEvents(a); setQuota(q); setBudget(b); setMembers(team); setCandidates(accounts); setError(null);
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
        <Metric label="Authentification" value={context ? AUTH_MODE_LABELS[context.auth_mode] : "…"} />
        <Metric label="Requêtes · p95" value={metrics ? `${metrics.requests_total ?? 0} · ${metrics.latency_p95_ms} ms` : "…"} />
        <Metric label="Jobs" value={metrics ? `${metrics.jobs_running} actif · ${metrics.jobs_failed} échoué` : "…"} />
      </>}
    </div>

    <section>
      <SectionTitle>Équipe et portabilité</SectionTitle>
      <Card className="mb-3 flex flex-wrap gap-2">
        {context?.auth_mode === "login" ? <>
          {/* Members are keyed on the account id: pick an existing account (managed in Utilisateurs). */}
          <Select value={candidateId} onChange={setCandidateId} disabled={busy} className="flex-1 min-w-56">
            <option value="">Choisir un compte…</option>
            {candidates.filter((c) => !members.some((m) => m.actor_id === c.id)).map((c) => <option key={c.id} value={c.id}>{c.name} · {c.email}</option>)}
          </Select>
          <Select value={candidateRole} onChange={(v) => setCandidateRole(v as RoleName)} disabled={busy}>
            {ROLE_NAMES.map((role) => <option key={role} value={role}>{ROLE_LABELS[role]}</option>)}
          </Select>
          <Button disabled={busy || !candidateId} onClick={() => act(async () => {
            const account = candidates.find((c) => c.id === candidateId)!;
            await api.enterprise.updateMember(projectId, { actor_id: account.id, email: account.email, name: account.name, role: candidateRole });
            setCandidateId("");
          })}>Ajouter au projet</Button>
        </> : <>
          <Input value={memberName} onChange={setMemberName} placeholder="Nom" className="min-w-40" />
          <Input value={memberEmail} onChange={setMemberEmail} placeholder="E-mail professionnel" className="flex-1 min-w-56" />
          <Button disabled={busy || !memberEmail.trim() || !memberName.trim()} onClick={() => act(async () => {
            const email = memberEmail.trim();
            await api.enterprise.updateMember(projectId, { actor_id: email.toLowerCase(), email, name: memberName.trim(), role: "viewer" });
            setMemberEmail(""); setMemberName("");
          })}>Ajouter comme viewer</Button>
        </>}
        <a href={api.enterprise.backupUrl(projectId)} className="px-3 py-1.5 text-sm rounded-md bg-surface-hover text-text-primary border border-border">Télécharger la sauvegarde</a>
      </Card>
      <div className="grid gap-2 md:grid-cols-2">{members.map((member) => <Card key={member.actor_id} className="flex items-center justify-between gap-3">
        <div className="min-w-0"><p className="text-sm text-text-primary">{member.name}</p><p className="text-xs text-text-muted truncate">{member.email}</p></div>
        <div className="flex items-center gap-1">
          <Select value={member.role} disabled={busy} className="text-xs" onChange={(v) => act(() => api.enterprise.updateMember(projectId, { actor_id: member.actor_id, email: member.email, name: member.name, role: v as ProjectMember["role"] }))}>
            {ROLE_NAMES.map((role) => <option key={role} value={role}>{ROLE_LABELS[role]}</option>)}
          </Select>
          {member.actor_id !== context?.actor.id && (
            <Button variant="ghost" className="text-xs" disabled={busy} onClick={() => act(() => api.enterprise.removeMember(projectId, member.actor_id))}>Retirer</Button>
          )}
        </div>
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
        <div className="flex gap-2">
          <a href={api.enterprise.sbomUrl(projectId, item.id)} download className="px-3 py-1.5 text-sm rounded-md font-medium border border-border hover:bg-surface-hover transition-colors">SBOM</a>
          {NEXT[item.status] ? <Button disabled={busy} onClick={() => act(() => api.enterprise.transition(projectId, item.id, NEXT[item.status]!))}>{item.status === "archived" ? "Rollback en production" : `Passer à « ${NEXT[item.status]} »`}</Button> : null}
        </div>
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
      <SectionTitle>Budget de l’agent (aujourd’hui)</SectionTitle>
      {budget ? <Card className="grid gap-4 sm:grid-cols-4 items-end">
        <QuotaInput label="Jetons / jour" value={budget.max_tokens_per_day} onChange={(v) => setBudget({ ...budget, max_tokens_per_day: v })} />
        <QuotaInput label="Durée (ms) / jour" value={budget.max_duration_ms_per_day} onChange={(v) => setBudget({ ...budget, max_duration_ms_per_day: v })} />
        <QuotaInput label="Appels d’outils / jour" value={budget.max_tool_calls_per_day} onChange={(v) => setBudget({ ...budget, max_tool_calls_per_day: v })} />
        <Button disabled={busy} onClick={() => act(() => api.enterprise.updateBudget(projectId, budget))}>Enregistrer</Button>
        <p className="text-xs text-text-muted sm:col-span-4">
          {budget.tokens_used ?? 0} / {budget.max_tokens_per_day} jetons · {budget.duration_ms_used ?? 0} / {budget.max_duration_ms_per_day} ms ·{" "}
          {budget.tool_calls_used ?? 0} / {budget.max_tool_calls_per_day} appels d’outils. Réinitialisé chaque jour (UTC) ; appliqué avant chaque échange de chat et chaque exécution d’outil.
        </p>
      </Card> : <EmptyState>Chargement du budget…</EmptyState>}
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
