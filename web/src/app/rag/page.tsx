"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { api, JobStatus, RAG_CATEGORIES, RagCategory, RagDocument, RagSearchResult } from "@/lib/api";
import { Button, Card, ConfirmDialog, EmptyState, Input, PageHeader, Pill, Select, SectionTitle, Skeleton, StatusBadge, Textarea } from "@/components/ui";
import { useProject } from "@/lib/project-context";
import { useAction } from "@/lib/use-action";

const CATEGORY_LABELS: Record<string, string> = {
  methods: "Méthodes d'organisation",
  research: "Études / recherche",
  product: "Documentation produit",
  other: "Autre",
};

function CategorySelect({ value, onChange }: { value: RagCategory; onChange: (v: RagCategory) => void }) {
  return (
    <Select value={value} onChange={(v) => onChange(v as RagCategory)}>
      {RAG_CATEGORIES.map((c) => (
        <option key={c} value={c}>
          {CATEGORY_LABELS[c]}
        </option>
      ))}
    </Select>
  );
}

export default function RagPage() {
  const { projectId } = useProject();
  const [documents, setDocuments] = useState<RagDocument[]>([]);
  const [reindexJob, setReindexJob] = useState<JobStatus | null>(null);

  const [uploadCategory, setUploadCategory] = useState<RagCategory>("research");
  const [newFilename, setNewFilename] = useState("");
  const [newCategory, setNewCategory] = useState<RagCategory>("other");
  const [newContent, setNewContent] = useState("");

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<RagSearchResult[] | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [loaded, setLoaded] = useState(false);

  const refresh = () => {
    if (!projectId) return;
    api.rag.documents(projectId).then((docs) => {
      setDocuments(docs);
      setLoaded(true);
    });
  };

  useEffect(() => {
    refresh();
  }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!reindexJob || reindexJob.status !== "running") return;
    const interval = setInterval(async () => {
      const updated = await api.jobs.get(reindexJob.job_id);
      setReindexJob(updated);
      if (updated.status !== "running") {
        clearInterval(interval);
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [reindexJob]);

  const grouped = useMemo(() => {
    const map = new Map<string, RagDocument[]>();
    for (const doc of documents) {
      if (!map.has(doc.category)) map.set(doc.category, []);
      map.get(doc.category)!.push(doc);
    }
    return map;
  }, [documents]);

  const trackReindexJob = (jobId: string | null | undefined) => {
    if (!jobId) return;
    api.jobs.get(jobId).then(setReindexJob);
  };

  const pasteAction = useAction(
    (filename: string, category: RagCategory, content: string) => api.rag.createDocument(projectId!, filename, category, content),
    { success: (doc) => `${doc.filename} ajouté.` },
  );
  const handlePaste = async () => {
    if (!newFilename.trim() || !newContent.trim() || !projectId) return;
    const filename = newFilename.trim().endsWith(".md") ? newFilename.trim() : `${newFilename.trim()}.md`;
    const doc = await pasteAction.run(filename, newCategory, newContent);
    if (doc) {
      setNewFilename("");
      setNewContent("");
      trackReindexJob(doc.reindex_job_id);
      refresh();
    }
  };

  const uploadAction = useAction((file: File, category: RagCategory) => api.rag.uploadDocument(projectId!, file, category), {
    success: (doc) => `${doc.filename} envoyé.`,
  });
  const handleFileUpload = async (file: File) => {
    if (!projectId) return;
    const doc = await uploadAction.run(file, uploadCategory);
    if (doc) {
      trackReindexJob(doc.reindex_job_id);
      refresh();
    }
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const [pendingDelete, setPendingDelete] = useState<{ category: string; filename: string } | null>(null);
  const deleteAction = useAction((category: string, filename: string) => api.rag.deleteDocument(projectId!, category, filename));
  const handleDelete = (category: string, filename: string) => setPendingDelete({ category, filename });
  const confirmDelete = async () => {
    if (!pendingDelete) return;
    const { category, filename } = pendingDelete;
    setPendingDelete(null);
    const res = await deleteAction.run(category, filename);
    if (res) {
      trackReindexJob(res.reindex_job_id);
      refresh();
    }
  };

  const reindexAction = useAction(() => api.rag.reindex(projectId!));
  const handleReindex = async () => {
    const job = await reindexAction.run();
    if (job) setReindexJob(job);
  };

  const handleSearch = async () => {
    if (!query.trim() || !projectId) return;
    setResults(await api.rag.search(projectId, query, 3));
  };

  return (
    <div className="space-y-10">
      <PageHeader
        title="RAG"
        description="Ajouter des documents de connaissance (méthodes, études, docs produit) — l'index se reconstruit automatiquement à chaque ajout/suppression."
        action={
          <div className="flex items-center gap-3">
            {reindexJob?.status === "running" && <StatusBadge status="running" />}
            <Button variant="ghost" onClick={handleReindex} disabled={reindexJob?.status === "running" || reindexAction.busy}>
              Forcer une reconstruction
            </Button>
          </div>
        }
      />

      <ConfirmDialog
        open={!!pendingDelete}
        title="Supprimer ce document ?"
        description={pendingDelete ? pendingDelete.filename : undefined}
        confirmLabel="Supprimer"
        danger
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />

      {reindexJob?.status === "running" && (
        <Card className="border-info/30 bg-info-soft text-text-secondary text-sm">
          Index en reconstruction automatique (job {reindexJob.job_id})…
        </Card>
      )}
      {reindexJob?.status === "completed" && (
        <Card className="border-success/30 bg-success-soft text-success text-sm">
          Index à jour (job {reindexJob.job_id}).
        </Card>
      )}
      {reindexJob?.status === "failed" && (
        <Card className="border-error/30 bg-error-soft text-error text-sm">
          Échec de la reconstruction automatique de l&apos;index (job {reindexJob.job_id}) — voir les logs du serveur.
        </Card>
      )}

      {grouped.has("research") && (
        <Card className="border-info/30 bg-info-soft text-text-secondary text-sm">
          Les documents « Études / recherche » servent de contexte à la génération. Vérifie leurs sources et définis
          dans la mission du projet les limites que le modèle doit respecter : le RAG apporte de l’information, il ne
          remplace pas les règles du modèle.
        </Card>
      )}

      {!loaded ? (
        <Skeleton className="h-32" />
      ) : (
        <>
          {RAG_CATEGORIES.map((cat) => {
            const docs = grouped.get(cat) ?? [];
            if (docs.length === 0) return null;
            return (
              <section key={cat}>
                <SectionTitle>
                  {CATEGORY_LABELS[cat]} ({docs.length})
                </SectionTitle>
                <div className="space-y-2">
                  {docs.map((doc) => (
                    <Card key={`${doc.category}/${doc.filename}`} className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <Pill>{doc.filename}</Pill>
                        <div className="flex items-center gap-3">
                          <span className="text-text-muted text-xs font-mono">{doc.char_count} chars</span>
                          <button
                            onClick={() => handleDelete(doc.category, doc.filename)}
                            className="text-error/80 hover:text-error text-xs font-medium transition-colors"
                          >
                            Supprimer
                          </button>
                        </div>
                      </div>
                      <p className="text-text-secondary text-sm leading-relaxed line-clamp-2">{doc.preview}</p>
                    </Card>
                  ))}
                </div>
              </section>
            );
          })}
          {documents.length === 0 && <EmptyState>Aucun document. Ajoute-en un ci-dessous.</EmptyState>}
        </>
      )}

      <section className="border-t border-border pt-6 space-y-6">
        <SectionTitle>Ajouter un document</SectionTitle>

        <Card className="space-y-3">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <p className="text-text-secondary text-sm">Envoyer un fichier — PDF, TXT ou MD (25 MB max, texte extrait automatiquement)</p>
            <CategorySelect value={uploadCategory} onChange={setUploadCategory} />
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.txt,.md"
            disabled={uploadAction.busy}
            onChange={(e) => e.target.files?.[0] && handleFileUpload(e.target.files[0])}
            className="text-sm text-text-secondary file:mr-3 file:px-3 file:py-1.5 file:rounded-md file:border-0 file:bg-surface-hover file:text-text-primary file:text-sm hover:file:bg-border cursor-pointer disabled:opacity-50"
          />
          {uploadAction.busy && <p className="text-text-muted text-xs">Extraction du texte…</p>}
        </Card>

        <Card className="space-y-3">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <p className="text-text-secondary text-sm">…ou coller le texte directement</p>
            <CategorySelect value={newCategory} onChange={setNewCategory} />
          </div>
          <Input value={newFilename} onChange={setNewFilename} placeholder="nom_du_document.md" />
          <Textarea value={newContent} onChange={setNewContent} placeholder="# Titre&#10;&#10;Contenu du document en markdown…" rows={6} className="font-mono" />
          <Button onClick={handlePaste} disabled={pasteAction.busy}>{pasteAction.busy ? "Ajout…" : "Ajouter"}</Button>
        </Card>
      </section>

      <section className="border-t border-border pt-6">
        <SectionTitle>Tester la recherche</SectionTitle>
        <div className="flex gap-2 mb-4">
          <Input
            value={query}
            onChange={setQuery}
            placeholder="Ex : comment prioriser urgent et important ?"
            className="flex-1"
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          />
          <Button onClick={handleSearch}>Chercher</Button>
        </div>
        {results && (
          <div className="space-y-2">
            {results.length === 0 && <EmptyState>Aucun résultat au-dessus du seuil.</EmptyState>}
            {results.map((r) => (
              <Card key={r.chunk_id} className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Pill>{r.doc_id}</Pill>
                    <span className="text-text-muted text-xs">{CATEGORY_LABELS[r.category] ?? r.category}</span>
                  </div>
                  <span className="text-accent text-xs font-mono">{r.score.toFixed(3)}</span>
                </div>
                <p className="text-text-secondary text-sm leading-relaxed line-clamp-3">{r.text}</p>
              </Card>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
