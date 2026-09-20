"use client";

import { useEffect, useRef, useState } from "react";
import { useProject } from "@/lib/project-context";
import { api, Project } from "@/lib/api";
import { Input, Select, Textarea } from "@/components/ui";
import { useAction } from "@/lib/use-action";

const PROJECT_TYPES: { value: Project["project_type"]; label: string; example: string }[] = [
  { value: "general", label: "Sur mesure", example: "Ex. : aider des étudiants à réviser leurs examens" },
  { value: "agent", label: "Agent IA", example: "Ex. : analyser des tickets puis proposer l’action à exécuter" },
  { value: "developer", label: "Assistant développeur", example: "Ex. : corriger et expliquer du code TypeScript" },
  { value: "business", label: "Assistant entreprise", example: "Ex. : aider le support client à rédiger des réponses" },
];

export function ProjectSwitcher() {
  const { projectId, projects, loading, error: projectError, setProjectId, refresh } = useProject();
  const [open, setOpen] = useState(false);
  const [newId, setNewId] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [newBaseModel, setNewBaseModel] = useState("");
  const [projectType, setProjectType] = useState<Project["project_type"]>("general");
  const [purpose, setPurpose] = useState("");
  const [outputMode, setOutputMode] = useState<Project["output_mode"]>("natural");
  const [modelKind, setModelKind] = useState<Project["model_kind"]>("generation");
  const [systemPrompt, setSystemPrompt] = useState("");
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    dialogRef.current?.focus();
    const onEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onEscape);
    return () => document.removeEventListener("keydown", onEscape);
  }, [open]);
  const createAction = useAction((params: Parameters<typeof api.projects.create>[0]) => api.projects.create(params), {
    success: (created) => `Projet « ${created.label} » créé.`,
  });
  const create = async () => {
    if (!newId.trim() || !newBaseModel.trim() || !purpose.trim()) return;
    const created = await createAction.run({
      id: newId.trim(),
      label: newLabel.trim() || undefined,
      base_model: newBaseModel.trim(),
      project_type: projectType,
      model_kind: modelKind,
      purpose: purpose.trim(),
      output_mode: modelKind === "decision" ? "json" : outputMode,
      system_prompt: systemPrompt.trim() || undefined,
    });
    if (created) {
      setNewId("");
      setNewLabel("");
      setNewBaseModel("");
      setPurpose("");
      setSystemPrompt("");
      setOpen(false);
      refresh();
      setProjectId(created.id);
    }
  };

  return (
    <div className="flex items-center gap-2 ml-auto">
      <Select
        value={projectId ?? ""}
        onChange={setProjectId}
        className="max-w-[220px]"
        disabled={loading}
      >
        {projects.length === 0 && <option value="">aucun projet</option>}
        {projects.map((proj) => (
          <option key={proj.id} value={proj.id}>
            {proj.label}
          </option>
        ))}
      </Select>
      {projectError && (
        <button type="button" onClick={refresh} className="text-error text-xs hover:underline" title={projectError}>
          API indisponible — réessayer
        </button>
      )}
      <button
        onClick={() => setOpen((v) => !v)}
        className="text-text-secondary hover:text-text-primary text-sm px-2 py-1 rounded-md hover:bg-surface-hover transition-colors"
        title="Nouveau projet"
      >
        +
      </button>
      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={() => setOpen(false)}>
          <div
            ref={dialogRef}
            tabIndex={-1}
            role="dialog"
            aria-modal="true"
            aria-labelledby="new-project-title"
            className="bg-surface border border-border rounded-lg p-4 space-y-3 shadow-lg w-[min(26rem,calc(100vw-2rem))] max-h-[calc(100vh-5rem)] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
          <h2 id="new-project-title" className="font-display text-base text-text-primary">Nouveau projet</h2>
          <p className="text-text-muted text-xs">
            Crée un modèle pour n’importe quel usage. Sa mission, ses données, son RAG et ses adapters resteront isolés.
          </p>
          {createAction.error && <p className="text-error text-xs">{createAction.error}</p>}
          <label className="block text-xs text-text-muted space-y-1">
            Nature du modèle
            <Select value={modelKind} onChange={(v) => setModelKind(v as Project["model_kind"])} className="w-full">
              <option value="generation">Génération (texte libre)</option>
              <option value="decision">Decision Model (décision structurée + confiance)</option>
            </Select>
          </label>
          <label className="block text-xs text-text-muted space-y-1">
            Type de modèle
            <Select value={projectType} onChange={(v) => setProjectType(v as Project["project_type"])} className="w-full">
              {PROJECT_TYPES.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}
            </Select>
          </label>
          <Textarea
            value={purpose}
            onChange={setPurpose}
            rows={3}
            maxLength={2000}
            placeholder={PROJECT_TYPES.find((type) => type.value === projectType)?.example}
          />
          <Input value={newLabel} onChange={setNewLabel} placeholder="Nom affiché (ex. Assistant support)" className="w-full" />
          <Input value={newId} onChange={setNewId} placeholder="id-du-projet (minuscules, tirets)" className="w-full" />
          <Input value={newBaseModel} onChange={setNewBaseModel} placeholder="org/nom-du-modele (HF)" className="w-full" />
          <label className="block text-xs text-text-muted space-y-1">
            Format de réponse
            <Select value={modelKind === "decision" ? "json" : outputMode} onChange={(v) => setOutputMode(v as Project["output_mode"])} className="w-full" disabled={modelKind === "decision"}>
              <option value="natural">Texte naturel</option>
              <option value="json">JSON pour une application ou un agent</option>
              <option value="flexible">Flexible selon la demande</option>
            </Select>
          </label>
          <details className="text-xs text-text-muted">
            <summary className="cursor-pointer hover:text-text-secondary">Instructions système personnalisées (optionnel)</summary>
            <Textarea
              value={systemPrompt}
              onChange={setSystemPrompt}
              rows={5}
              maxLength={12000}
              placeholder="Laisse vide pour générer les instructions depuis la mission."
              className="mt-2"
            />
          </details>
          <div className="flex gap-2">
            <button
              onClick={create}
              disabled={createAction.busy || !newId.trim() || !newBaseModel.trim() || !purpose.trim()}
              className="flex-1 bg-accent text-white hover:bg-accent-strong disabled:opacity-40 px-3 py-1.5 text-sm rounded-md font-medium transition-colors"
            >
              {createAction.busy ? "Création…" : "Créer"}
            </button>
            <button
              onClick={() => setOpen(false)}
              className="text-text-secondary hover:text-text-primary text-sm px-3 py-1.5 rounded-md hover:bg-surface-hover transition-colors"
            >
              Annuler
            </button>
          </div>
          </div>
        </div>
      )}
    </div>
  );
}
