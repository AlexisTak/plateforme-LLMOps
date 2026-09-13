"use client";

import { useEffect, useMemo, useState } from "react";
import { api, CurrentDatasetVersion, DatasetCategorySummary, DatasetExample, Message, ValidationResult, DatasetStats } from "@/lib/api";
import { Button, Card, EmptyState, Input, PageHeader, Pill, SectionTitle } from "@/components/ui";
import { BarChart } from "@/components/bar-chart";
import { useProject } from "@/lib/project-context";

const ROLES: Message["role"][] = ["user", "assistant"];

export default function DatasetPage() {
  const { projectId } = useProject();
  const [categories, setCategories] = useState<DatasetCategorySummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [examples, setExamples] = useState<DatasetExample[]>([]);
  const [stats, setStats] = useState<DatasetStats | null>(null);
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [prepareVersion, setPrepareVersion] = useState("dataset-v0.4");
  const [prepareResult, setPrepareResult] = useState<string | null>(null);
  const [dedupResult, setDedupResult] = useState<string | null>(null);
  const [currentVersion, setCurrentVersion] = useState<CurrentDatasetVersion | null>(null);
  const [query, setQuery] = useState("");
  const [addingNew, setAddingNew] = useState(false);

  const refreshCategories = () => {
    if (!projectId) return;
    api.dataset.categories(projectId).then(setCategories);
    api.dataset.stats(projectId).then(setStats);
  };

  const refreshVersion = () => {
    if (!projectId) return;
    api.dataset.currentVersion(projectId).then(setCurrentVersion);
  };

  useEffect(() => {
    refreshCategories();
    refreshVersion();
  }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (selected && projectId) api.dataset.list(projectId, selected).then(setExamples);
  }, [selected, projectId]);

  const runValidate = async () => {
    if (!projectId) return;
    setBusy(true);
    try {
      setValidation(await api.dataset.validate(projectId));
    } finally {
      setBusy(false);
    }
  };

  const runPrepare = async () => {
    if (!projectId) return;
    setBusy(true);
    setPrepareResult(null);
    try {
      const res = await api.dataset.prepare(projectId, prepareVersion);
      setPrepareResult(`${res.version} — train ${res.train} · validation ${res.validation} · test ${res.test}`);
      refreshVersion();
    } finally {
      setBusy(false);
    }
  };

  const runDeduplicate = async () => {
    if (!projectId) return;
    setBusy(true);
    setDedupResult(null);
    try {
      const preview = await api.dataset.deduplicate(projectId, true);
      if (preview.duplicates.length === 0) {
        setDedupResult("Aucun doublon exact trouvé.");
        return;
      }
      const sample = preview.duplicates.slice(0, 10).map((d) => `${d.file}:${d.line}`).join(", ");
      const more = preview.duplicates.length > 10 ? ` (+${preview.duplicates.length - 10} autre(s))` : "";
      if (!confirm(`${preview.duplicates.length} doublon(s) exact(s) trouvé(s) sur ${preview.total_before} exemples :\n${sample}${more}\n\nLes supprimer ?`)) {
        setDedupResult(`${preview.duplicates.length} doublon(s) détecté(s), non supprimé(s) (annulé).`);
        return;
      }
      const res = await api.dataset.deduplicate(projectId, false);
      setDedupResult(`${res.removed} doublon(s) exact(s) supprimé(s) sur ${res.total_before} exemples.`);
      refreshCategories();
      if (selected) api.dataset.list(projectId, selected).then(setExamples);
    } finally {
      setBusy(false);
    }
  };

  const deleteExample = async (ex: DatasetExample) => {
    if (!selected || !projectId) return;
    if (!confirm(`Supprimer l'exemple #${ex.index} de ${ex.file} ?`)) return;
    await api.dataset.remove(projectId, selected, ex.id);
    api.dataset.list(projectId, selected).then(setExamples);
    refreshCategories();
  };

  const saveExample = async (ex: DatasetExample, messages: Message[]) => {
    if (!selected || !projectId) return;
    await api.dataset.update(projectId, selected, ex.id, messages);
    api.dataset.list(projectId, selected).then(setExamples);
    refreshCategories();
  };

  const addExample = async (file: string, messages: Message[]) => {
    if (!selected || !projectId) return;
    await api.dataset.add(projectId, selected, file, messages);
    setAddingNew(false);
    api.dataset.list(projectId, selected).then(setExamples);
    refreshCategories();
  };

  const filteredExamples = useMemo(() => {
    if (!query.trim()) return examples;
    const q = query.trim().toLowerCase();
    return examples.filter((ex) => ex.messages.some((m) => m.content.toLowerCase().includes(q)));
  }, [examples, query]);

  return (
    <div className="space-y-8">
      <PageHeader
        title="Dataset"
        description="Parcourir, éditer et ajouter des exemples par catégorie, valider le format, dédupliquer, reconstruire les splits."
        action={
          <div className="flex items-center gap-2">
            <Button variant="ghost" onClick={runDeduplicate} disabled={busy}>
              Dédupliquer
            </Button>
            <Button onClick={runValidate} disabled={busy}>
              Valider le dataset
            </Button>
          </div>
        }
      />

      <div className="grid grid-cols-4 gap-4">
        <Card>
          <p className="text-text-muted text-xs uppercase tracking-wide mb-1">Version active</p>
          <p className="font-display text-2xl text-accent font-mono truncate" title={currentVersion?.version ?? undefined}>
            {currentVersion?.version ?? "—"}
          </p>
          <p className="text-text-muted text-xs mt-1">
            {currentVersion ? `${currentVersion.train}/${currentVersion.validation}/${currentVersion.test}` : "pas encore reconstruit"}
          </p>
        </Card>
        {stats && (
          <>
            <Card>
              <p className="text-text-muted text-xs uppercase tracking-wide mb-1">Exemples</p>
              <p className="font-display text-3xl text-text-primary">{stats.total_examples}</p>
            </Card>
            <Card>
              <p className="text-text-muted text-xs uppercase tracking-wide mb-1">Longueur moyenne</p>
              <p className="font-display text-3xl text-text-primary">
                {stats.char_length_mean}
                <span className="text-sm text-text-muted ml-1">chars</span>
              </p>
              <p className="text-text-muted text-xs mt-1">p95 {stats.char_length_p95}</p>
            </Card>
            <Card>
              <p className="text-text-muted text-xs uppercase tracking-wide mb-1">Doublons exacts</p>
              <p className={`font-display text-3xl ${stats.exact_duplicates > 0 ? "text-error" : "text-success"}`}>
                {stats.exact_duplicates}
              </p>
            </Card>
          </>
        )}
      </div>

      {dedupResult && <Card className="border-success/30 bg-success-soft text-success text-sm">{dedupResult}</Card>}

      {validation && (
        <Card className={validation.errors > 0 ? "border-error/30 bg-error-soft" : "border-success/30 bg-success-soft"}>
          <p className={`text-sm font-medium ${validation.errors > 0 ? "text-error" : "text-success"}`}>
            {validation.total_examples} exemples, {validation.total_files} fichiers — {validation.errors} erreur(s), {validation.warnings} avertissement(s)
          </p>
          {validation.findings.length > 0 && (
            <ul className="mt-3 space-y-1 max-h-48 overflow-y-auto font-mono text-xs">
              {validation.findings.map((f, i) => (
                <li key={i} className={f.level === "error" ? "text-error" : "text-accent"}>
                  [{f.level}] {f.file}:{f.line} — {f.message}
                </li>
              ))}
            </ul>
          )}
          {validation.split_leaks.length > 0 && (
            <div className="mt-3 pt-3 border-t border-border/50">
              <p className="text-xs font-medium text-error">
                Fuite train/test : {validation.split_leaks.length} exemple(s) présent(s) à la fois dans train et un autre split (informatif — reconstruire les splits ne les corrigera pas seul).
              </p>
              <ul className="mt-1 space-y-1 max-h-40 overflow-y-auto font-mono text-xs text-text-secondary">
                {validation.split_leaks.slice(0, 20).map((l, i) => (
                  <li key={i}>
                    {l.train_ref} ≈ {l.split_ref}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {(validation.near_duplicates.length > 0 || validation.near_duplicate_scan_skipped) && (
            <div className="mt-3 pt-3 border-t border-border/50">
              <p className="text-xs font-medium text-accent">
                {validation.near_duplicate_scan_skipped
                  ? "Dataset trop volumineux pour le scan de quasi-doublons (informatif, ignoré)."
                  : `Quasi-doublons : ${validation.near_duplicates.length} paire(s) similaires (≥90%) — informatif, rien n'a été supprimé.`}
              </p>
              {validation.near_duplicates.length > 0 && (
                <ul className="mt-1 space-y-1 max-h-40 overflow-y-auto font-mono text-xs text-text-secondary">
                  {validation.near_duplicates.slice(0, 20).map((d, i) => (
                    <li key={i}>
                      {d.file_a}:{d.line_a} ≈ {d.file_b}:{d.line_b} ({Math.round(d.similarity * 100)}%)
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </Card>
      )}

      {categories.length > 0 && (
        <section>
          <SectionTitle>Répartition par catégorie</SectionTitle>
          <Card>
            <BarChart data={categories.map((c) => ({ label: c.category, value: c.example_count }))} formatValue={(v) => String(v)} />
          </Card>
        </section>
      )}

      <div className="grid grid-cols-[220px_1fr] gap-6">
        <div className="space-y-1">
          {categories.map((cat) => (
            <button
              key={cat.category}
              onClick={() => {
                setSelected(cat.category);
                setAddingNew(false);
              }}
              className={`w-full flex items-center justify-between text-left px-3 py-2 rounded-md text-sm transition-colors ${
                selected === cat.category ? "bg-accent-soft text-accent-strong" : "text-text-secondary hover:bg-surface-hover hover:text-text-primary"
              }`}
            >
              <span>{cat.category}</span>
              <span className="font-mono text-xs opacity-70">{cat.example_count}</span>
            </button>
          ))}
        </div>

        <div className="space-y-3 min-w-0">
          {selected ? (
            <>
              <div className="flex items-center gap-2">
                <Input value={query} onChange={setQuery} placeholder="Rechercher dans cette catégorie…" className="flex-1" />
                <Button variant="accent" onClick={() => setAddingNew((v) => !v)}>
                  {addingNew ? "Annuler" : "+ Ajouter"}
                </Button>
              </div>

              {addingNew && <NewExampleCard defaultFile={`${selected}.jsonl`} onSave={addExample} onCancel={() => setAddingNew(false)} />}

              {query.trim() && (
                <p className="text-text-muted text-xs">
                  {filteredExamples.length} résultat(s) sur {examples.length}
                </p>
              )}

              {filteredExamples.length === 0 && !addingNew ? (
                <EmptyState>{query.trim() ? "Aucun résultat." : "Aucun exemple dans cette catégorie."}</EmptyState>
              ) : (
                filteredExamples.map((ex) => (
                  <ExampleCard key={ex.id} example={ex} onDelete={() => deleteExample(ex)} onSave={(msgs) => saveExample(ex, msgs)} />
                ))
              )}
            </>
          ) : (
            <EmptyState>Sélectionne une catégorie à gauche.</EmptyState>
          )}
        </div>
      </div>

      <section className="border-t border-border pt-6">
        <SectionTitle>Reconstruire les splits</SectionTitle>
        <p className="text-text-secondary text-sm mb-3">Régénère train / validation / test (80/10/10) à partir de tout le contenu de <code className="font-mono text-text-primary">datasets/</code>.</p>
        <div className="flex items-center gap-2">
          <Input value={prepareVersion} onChange={setPrepareVersion} placeholder="dataset-v0.4" className="w-48" />
          <Button onClick={runPrepare} disabled={busy}>
            Reconstruire
          </Button>
          {prepareResult && <span className="text-sm text-text-secondary font-mono">{prepareResult}</span>}
        </div>
      </section>
    </div>
  );
}

function ExampleCard({
  example,
  onDelete,
  onSave,
}: {
  example: DatasetExample;
  onDelete: () => void;
  onSave: (messages: Message[]) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Message[]>(example.messages);
  const [saving, setSaving] = useState(false);

  const startEdit = () => {
    setDraft(example.messages.map((m) => ({ ...m })));
    setEditing(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      await onSave(draft);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  if (editing) {
    return (
      <Card className="space-y-2.5 border-accent/40">
        <div className="flex items-center justify-between">
          <Pill>
            {example.file}#{example.index}
          </Pill>
          <div className="flex items-center gap-3 text-xs">
            <button onClick={() => setEditing(false)} className="text-text-muted hover:text-text-primary transition-colors">
              Annuler
            </button>
            <button onClick={save} disabled={saving} className="text-accent hover:text-accent-strong font-medium transition-colors disabled:opacity-50">
              Enregistrer
            </button>
          </div>
        </div>
        {draft.map((m, i) => (
          <div key={i} className="flex gap-3 text-sm items-start">
            <span className="text-text-muted uppercase text-[11px] tracking-wide w-16 shrink-0 pt-1.5 font-medium">{m.role}</span>
            <textarea
              value={m.content}
              onChange={(e) => {
                const next = [...draft];
                next[i] = { ...next[i], content: e.target.value };
                setDraft(next);
              }}
              rows={3}
              className="flex-1 bg-bg border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary focus:outline-none focus:border-accent transition-colors font-mono"
            />
          </div>
        ))}
      </Card>
    );
  }

  return (
    <Card className="space-y-2.5">
      <div className="flex items-center justify-between">
        <Pill>
          {example.file}#{example.index}
        </Pill>
        <div className="flex items-center gap-3 text-xs">
          <button onClick={startEdit} className="text-text-secondary hover:text-text-primary font-medium transition-colors">
            Éditer
          </button>
          <button onClick={onDelete} className="text-error/80 hover:text-error font-medium transition-colors">
            Supprimer
          </button>
        </div>
      </div>
      {example.messages.map((m: Message, i: number) => (
        <div key={i} className="flex gap-3 text-sm">
          <span className="text-text-muted uppercase text-[11px] tracking-wide w-16 shrink-0 pt-0.5 font-medium">{m.role}</span>
          <span className="whitespace-pre-wrap break-words text-text-primary leading-relaxed">{m.content}</span>
        </div>
      ))}
    </Card>
  );
}

function NewExampleCard({
  defaultFile,
  onSave,
  onCancel,
}: {
  defaultFile: string;
  onSave: (file: string, messages: Message[]) => Promise<void>;
  onCancel: () => void;
}) {
  const [file, setFile] = useState(defaultFile);
  const [userContent, setUserContent] = useState("");
  const [assistantContent, setAssistantContent] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    if (!userContent.trim() || !assistantContent.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await onSave(file.trim(), [
        { role: "user", content: userContent.trim() },
        { role: "assistant", content: assistantContent.trim() },
      ]);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="space-y-2.5 border-accent/40">
      <p className="text-text-muted text-xs uppercase tracking-wide">Nouvel exemple</p>
      {error && <p className="text-error text-xs">{error}</p>}
      <Input value={file} onChange={setFile} placeholder="fichier.jsonl" className="w-56" />
      {ROLES.map((role) => (
        <div key={role} className="flex gap-3 text-sm items-start">
          <span className="text-text-muted uppercase text-[11px] tracking-wide w-16 shrink-0 pt-1.5 font-medium">{role}</span>
          <textarea
            value={role === "user" ? userContent : assistantContent}
            onChange={(e) => (role === "user" ? setUserContent(e.target.value) : setAssistantContent(e.target.value))}
            rows={3}
            placeholder={role === "user" ? "Message utilisateur…" : 'Réponse assistant… (JSON si structuré, ex: {"intent": "..."})'}
            className="flex-1 bg-bg border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors font-mono"
          />
        </div>
      ))}
      <div className="flex items-center gap-2">
        <Button variant="accent" onClick={save} disabled={saving || !userContent.trim() || !assistantContent.trim()}>
          Ajouter
        </Button>
        <Button variant="ghost" onClick={onCancel}>
          Annuler
        </Button>
      </div>
    </Card>
  );
}
