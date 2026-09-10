"use client";

import { useState } from "react";
import { useProject } from "@/lib/project-context";
import { api, Project } from "@/lib/api";

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
  const [systemPrompt, setSystemPrompt] = useState("");
  const [error, setError] = useState<string | null>(null);

  const create = async () => {
    setError(null);
    if (!newId.trim() || !newBaseModel.trim() || !purpose.trim()) return;
    try {
      const created = await api.projects.create({
        id: newId.trim(),
        label: newLabel.trim() || undefined,
        base_model: newBaseModel.trim(),
        project_type: projectType,
        purpose: purpose.trim(),
        output_mode: outputMode,
        system_prompt: systemPrompt.trim() || undefined,
      });
      setNewId("");
      setNewLabel("");
      setNewBaseModel("");
      setPurpose("");
      setSystemPrompt("");
      setOpen(false);
      refresh();
      setProjectId(created.id);
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <div className="flex items-center gap-2 ml-auto">
      <select
        value={projectId ?? ""}
        onChange={(e) => setProjectId(e.target.value)}
        className="bg-surface border border-border rounded-md px-2.5 py-1 text-sm text-text-primary focus:outline-none focus:border-accent transition-colors max-w-[220px]"
        disabled={loading}
        title={projectError ? `API indisponible : ${projectError}` : "Projet actif — dataset, RAG, configs et expériences isolés par projet"}
      >
        {projects.length === 0 && <option value="">aucun projet</option>}
        {projects.map((proj) => (
          <option key={proj.id} value={proj.id}>
            {proj.label}
          </option>
        ))}
      </select>
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
        <div className="absolute top-14 right-4 sm:right-6 bg-surface border border-border rounded-lg p-4 space-y-3 shadow-lg z-20 w-[min(26rem,calc(100vw-2rem))] max-h-[calc(100vh-5rem)] overflow-y-auto">
          <p className="text-text-muted text-xs">
            Crée un modèle pour n’importe quel usage. Sa mission, ses données, son RAG et ses adapters resteront isolés.
          </p>
          {error && <p className="text-error text-xs">{error}</p>}
          <label className="block text-xs text-text-muted space-y-1">
            Type de modèle
            <select
              value={projectType}
              onChange={(e) => setProjectType(e.target.value as Project["project_type"])}
              className="w-full bg-bg border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary focus:outline-none focus:border-accent"
            >
              {PROJECT_TYPES.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}
            </select>
          </label>
          <textarea
            value={purpose}
            onChange={(e) => setPurpose(e.target.value)}
            rows={3}
            maxLength={2000}
            placeholder={PROJECT_TYPES.find((type) => type.value === projectType)?.example}
            aria-label="Mission du modèle"
            className="w-full bg-bg border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors resize-y"
          />
          <input
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
            placeholder="Nom affiché (ex. Assistant support)"
            className="w-full bg-bg border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors"
          />
          <input
            value={newId}
            onChange={(e) => setNewId(e.target.value)}
            placeholder="id-du-projet (minuscules, tirets)"
            className="w-full bg-bg border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors"
          />
          <input
            value={newBaseModel}
            onChange={(e) => setNewBaseModel(e.target.value)}
            placeholder="org/nom-du-modele (HF)"
            className="w-full bg-bg border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors"
          />
          <label className="block text-xs text-text-muted space-y-1">
            Format de réponse
            <select
              value={outputMode}
              onChange={(e) => setOutputMode(e.target.value as Project["output_mode"])}
              className="w-full bg-bg border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary focus:outline-none focus:border-accent"
            >
              <option value="natural">Texte naturel</option>
              <option value="json">JSON pour une application ou un agent</option>
              <option value="flexible">Flexible selon la demande</option>
            </select>
          </label>
          <details className="text-xs text-text-muted">
            <summary className="cursor-pointer hover:text-text-secondary">Instructions système personnalisées (optionnel)</summary>
            <textarea
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              rows={5}
              maxLength={12000}
              placeholder="Laisse vide pour générer les instructions depuis la mission."
              className="w-full mt-2 bg-bg border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors resize-y"
            />
          </details>
          <div className="flex gap-2">
            <button
              onClick={create}
              disabled={!newId.trim() || !newBaseModel.trim() || !purpose.trim()}
              className="flex-1 bg-accent text-[#20140a] hover:bg-accent-strong disabled:opacity-40 px-3 py-1.5 text-sm rounded-md font-medium transition-colors"
            >
              Créer
            </button>
            <button
              onClick={() => setOpen(false)}
              className="text-text-secondary hover:text-text-primary text-sm px-3 py-1.5 rounded-md hover:bg-surface-hover transition-colors"
            >
              Annuler
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
