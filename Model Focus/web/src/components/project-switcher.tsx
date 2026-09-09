"use client";

import { useState } from "react";
import { useProject } from "@/lib/project-context";
import { api } from "@/lib/api";

export function ProjectSwitcher() {
  const { projectId, projects, loading, error: projectError, setProjectId, refresh } = useProject();
  const [open, setOpen] = useState(false);
  const [newId, setNewId] = useState("");
  const [newBaseModel, setNewBaseModel] = useState("");
  const [error, setError] = useState<string | null>(null);

  const create = async () => {
    setError(null);
    if (!newId.trim() || !newBaseModel.trim()) return;
    try {
      const created = await api.projects.create(newId.trim(), newBaseModel.trim());
      setNewId("");
      setNewBaseModel("");
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
        <div className="absolute top-14 right-6 bg-surface border border-border rounded-lg p-3 space-y-2 shadow-lg z-20 w-72">
          <p className="text-text-muted text-xs">
            Un nouveau projet = un dataset, un RAG et des expériences complètement isolés — comme changer de compte.
          </p>
          {error && <p className="text-error text-xs">{error}</p>}
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
          <div className="flex gap-2">
            <button
              onClick={create}
              disabled={!newId.trim() || !newBaseModel.trim()}
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
