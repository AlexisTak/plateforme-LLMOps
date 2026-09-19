"use client";

import { useCallback, useEffect, useState } from "react";
import { api, Project, ProjectSettings } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import { Button, Card, Field, PageHeader, Select, SectionTitle, Skeleton, Textarea } from "@/components/ui";
import { useAction } from "@/lib/use-action";
import { humanError } from "@/lib/errors";

const TYPES: { value: Project["project_type"]; label: string }[] = [
  { value: "general", label: "Sur mesure" }, { value: "agent", label: "Agent IA" },
  { value: "developer", label: "Assistant développeur" }, { value: "business", label: "Assistant entreprise" },
];

export default function SettingsPage() {
  const { projectId, refresh: refreshProjects } = useProject();
  return projectId ? <ProjectSettingsForm key={projectId} projectId={projectId} refreshProjects={refreshProjects} /> : <p>Sélectionne un projet.</p>;
}

function ProjectSettingsForm({ projectId, refreshProjects }: { projectId: string; refreshProjects: () => void }) {
  const [settings, setSettings] = useState<ProjectSettings | null>(null);
  const [saved, setSaved] = useState<ProjectSettings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const value = await api.projects.settings(projectId);
    setSettings(value); setSaved(value); setLoadError(null);
  }, [projectId]);

  useEffect(() => { Promise.resolve().then(load).catch((e) => setLoadError(humanError(e))); }, [load]);

  const saveAction = useAction((value: ProjectSettings) => api.projects.updateSettings(projectId, value), {
    success: "Réglages enregistrés.",
  });
  const save = async () => {
    if (!settings) return;
    const value = await saveAction.run(settings);
    if (value) {
      setSettings(value);
      setSaved(value);
      refreshProjects();
    }
  };

  const changed = settings && saved && JSON.stringify(settings) !== JSON.stringify(saved);
  return <div className="space-y-8">
    <PageHeader title="Settings" description="Configuration du projet actif. Les changements de modèle, prompt, mission ou format rendent les anciens benchmarks obsolètes." action={<div className="flex gap-2"><Button disabled={!changed || saveAction.busy} onClick={() => saved && setSettings(saved)}>Annuler</Button><Button variant="accent" disabled={!changed || saveAction.busy} onClick={save}>{saveAction.busy ? "Enregistrement…" : "Enregistrer"}</Button></div>} />
    {loadError ? <Card className="border-error/30 bg-error-soft text-error text-sm">{loadError}</Card> : null}
    {saveAction.error ? <Card className="border-error/30 bg-error-soft text-error text-sm">{saveAction.error}</Card> : null}
    {!settings ? <div className="space-y-4"><Skeleton className="h-8 w-1/3" /><Skeleton className="h-48" /><Skeleton className="h-32" /></div> : <>
      <section><SectionTitle>Identité et mission</SectionTitle><Card className="space-y-4">
        <Field label="Identifiant technique"><input value={settings.id} disabled className="field opacity-60" /></Field>
        <Field label="Nom affiché"><input value={settings.label} maxLength={200} onChange={(e) => setSettings({ ...settings, label: e.target.value })} className="field" /></Field>
        <Field label="Type de projet"><Select value={settings.project_type} onChange={(v) => setSettings({ ...settings, project_type: v as Project["project_type"] })}>{TYPES.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}</Select></Field>
        <Field label="Mission"><Textarea value={settings.purpose} rows={4} maxLength={2000} onChange={(v) => setSettings({ ...settings, purpose: v })} /></Field>
      </Card></section>
      <section><SectionTitle>Modèle et réponses</SectionTitle><Card className="space-y-4">
        <Field label="Modèle de base"><input value={settings.base_model} disabled className="field opacity-60" /><span className="text-xs text-text-muted">Fixé à la création pour préserver la compatibilité des adapters.</span></Field>
        <Field label="Modèle d’inférence Hugging Face"><input value={settings.inference_model} onChange={(e) => setSettings({ ...settings, inference_model: e.target.value })} className="field font-mono" /></Field>
        <Field label="Format de réponse"><Select value={settings.output_mode} onChange={(v) => setSettings({ ...settings, output_mode: v as Project["output_mode"] })}><option value="natural">Texte naturel</option><option value="json">JSON</option><option value="flexible">Flexible</option></Select></Field>
        <Field label="Longueur maximale des réponses du dataset"><input type="number" min={100} max={100000} value={settings.max_assistant_chars} onChange={(e) => setSettings({ ...settings, max_assistant_chars: Number(e.target.value) })} className="field" /></Field>
      </Card></section>
      <section><SectionTitle>Instructions système</SectionTitle><Card><Textarea value={settings.system_prompt} rows={12} maxLength={12000} onChange={(v) => setSettings({ ...settings, system_prompt: v })} className="font-mono leading-relaxed" /><p className="text-xs text-text-muted mt-2">{settings.system_prompt.length} / 12 000 caractères</p></Card></section>
    </>}
    <style jsx>{`.field{width:100%;background:var(--bg);border:1px solid var(--border);border-radius:.375rem;padding:.5rem .75rem;color:var(--text-primary);font-size:.875rem}.field:focus{outline:none;border-color:var(--accent)}textarea.field{resize:vertical}`}</style>
  </div>;
}
