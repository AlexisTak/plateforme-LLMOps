"use client";

import { useCallback, useEffect, useState } from "react";
import { api, BenchmarkCase, EvalSummaryMetric, EvaluationReport, JobStatus, ModelPreflight } from "@/lib/api";
import { DonutChart } from "@/components/donut-chart";
import { Button, Card, ConfirmDialog, EmptyState, Input, PageHeader, Pill, SectionTitle, Skeleton, StatusBadge, Textarea } from "@/components/ui";
import { useProject } from "@/lib/project-context";
import { ModelPreflightCard } from "@/components/model-preflight-card";
import { useAction } from "@/lib/use-action";
import { humanError } from "@/lib/errors";

const legacyCount = (passed: number | undefined, percentage: number | null | undefined, total: number) =>
  passed ?? Math.round(((percentage ?? 0) / 100) * total);

export default function BenchmarksPage() {
  const { projectId, project } = useProject();
  return projectId && project ? <ProjectBenchmarks key={projectId} projectId={projectId} model={project.inference_model || project.base_model} /> : <p>Sélectionne un projet.</p>;
}

function ProjectBenchmarks({ projectId, model }: { projectId: string; model: string }) {
  const [cases, setCases] = useState<BenchmarkCase[]>([]);
  const [summary, setSummary] = useState<Record<string, EvalSummaryMetric> | null>(null);
  const [report, setReport] = useState<EvaluationReport | null>(null);
  const [job, setJob] = useState<JobStatus | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preflight, setPreflight] = useState<ModelPreflight | null>(null);
  const [preflightLoading, setPreflightLoading] = useState(true);
  const [editing, setEditing] = useState<BenchmarkCase | "new" | null>(null);
  const [casesLoaded, setCasesLoaded] = useState(false);
  const [pendingRemove, setPendingRemove] = useState<BenchmarkCase | null>(null);

  const checkModel = useCallback(() => {
    setPreflightLoading(true);
    return api.training.preflight(projectId, model).then(setPreflight).catch(() => setPreflight(null))
      .finally(() => setPreflightLoading(false));
  }, [model, projectId]);

  const refresh = useCallback(() => Promise.all([
      api.evaluation.benchmark(projectId),
      api.experiments.reportSummary(projectId).catch(() => null),
      api.experiments.report(projectId).catch(() => null),
    ]).then(([nextCases, nextSummary, nextReport]) => {
      setCases(nextCases);
      setSummary(nextSummary);
      setReport(nextReport);
      setCasesLoaded(true);
    }), [projectId]);

  useEffect(() => {
    refresh().catch((e) => setError(humanError(e)));
  }, [refresh]);

  useEffect(() => {
    api.training.preflight(projectId, model).then(setPreflight).catch(() => setPreflight(null))
      .finally(() => setPreflightLoading(false));
  }, [model, projectId]);

  useEffect(() => {
    if (!job || job.status !== "running") return;
    const interval = setInterval(() => {
      api.jobs.get(job.job_id).then((next) => {
        setJob(next);
        if (next.status !== "running") {
          setRunning(false);
          refresh().catch((e) => setError(humanError(e)));
        }
      }).catch((e) => { setRunning(false); setError(humanError(e)); });
    }, 3000);
    return () => clearInterval(interval);
  }, [job, refresh]);

  const run = async () => {
    setRunning(true);
    setError(null);
    try {
      setJob(await api.evaluation.run(projectId));
    } catch (e) {
      setRunning(false);
      setError(humanError(e));
    }
  };

  const saveCase = async (item: BenchmarkCase) => {
    setError(null);
    try {
      if (editing === "new") await api.evaluation.createCase(projectId, item);
      else if (editing) await api.evaluation.updateCase(projectId, editing.id, item);
      setEditing(null);
      await refresh();
    } catch (e) {
      setError(humanError(e));
      throw e;
    }
  };

  const removeCaseAction = useAction((item: BenchmarkCase) => api.evaluation.removeCase(projectId, item.id));
  const removeCase = (item: BenchmarkCase) => setPendingRemove(item);
  const confirmRemoveCase = async () => {
    if (!pendingRemove) return;
    const item = pendingRemove;
    setPendingRemove(null);
    const res = await removeCaseAction.run(item);
    if (res !== undefined) {
      if (editing !== "new" && editing?.id === item.id) setEditing(null);
      await refresh();
    }
  };

  const metrics = summary ? Object.entries(summary) : [];

  return (
    <div className="space-y-10">
      <PageHeader
        title="Benchmarks"
        description="Cas de test comportementaux, résultats automatiques et critères de revue humaine."
        action={<Button variant="accent" onClick={run} disabled={running || !preflight?.ready}>{running ? "Évaluation en cours…" : "Lancer le benchmark"}</Button>}
      />

      <ConfirmDialog
        open={!!pendingRemove}
        title="Supprimer ce cas ?"
        description={pendingRemove ? `Supprimer définitivement le cas « ${pendingRemove.id} ».` : undefined}
        confirmLabel="Supprimer"
        danger
        onConfirm={confirmRemoveCase}
        onCancel={() => setPendingRemove(null)}
      />

      <ModelPreflightCard result={preflight} loading={preflightLoading} onRetry={checkModel} />

      {error ? <Card className="border-error/30 bg-error-soft text-error text-sm">{error}</Card> : null}
      {job ? <Card className="flex items-center justify-between"><span className="font-mono text-sm">Job {job.job_id}</span><StatusBadge status={job.status} /></Card> : null}
      {job?.status === "failed" && job.error_message ? (
        <Card className="border-error/30 bg-error-soft text-sm"><p className="text-error font-medium">{job.error_message}</p>{job.suggestion ? <p className="text-text-secondary mt-1">{job.suggestion}</p> : null}</Card>
      ) : null}

      <section>
        <div className="flex items-center justify-between gap-3 mb-3">
          <SectionTitle>Cas de test ({cases.length})</SectionTitle>
          <Button variant="accent" onClick={() => setEditing(editing === "new" ? null : "new")}>{editing === "new" ? "Annuler" : "+ Nouveau cas"}</Button>
        </div>
        {editing ? <BenchmarkCaseEditor key={editing === "new" ? "new" : editing.id} initial={editing === "new" ? undefined : editing} onSave={saveCase} onCancel={() => setEditing(null)} /> : null}
        {!casesLoaded ? (
          <div className="grid gap-3 md:grid-cols-2">
            <Skeleton className="h-24" />
            <Skeleton className="h-24" />
          </div>
        ) : cases.length === 0 ? <EmptyState>Aucun cas de benchmark.</EmptyState> : (
          <div className="grid gap-3 md:grid-cols-2">
            {cases.map((item) => (
              <details key={item.id} className="group bg-surface border border-border rounded-lg p-4">
                <summary className="cursor-pointer list-none flex items-center justify-between gap-3">
                  <span className="font-medium text-sm text-text-primary">{item.id}</span>
                  <Pill>{item.category}</Pill>
                </summary>
                <div className="pt-4 space-y-3 text-sm">
                  <p className="text-text-secondary">{item.user}</p>
                  <div>
                    <p className="text-text-muted text-xs uppercase tracking-wide mb-1">Critères de revue</p>
                    <ul className="list-disc pl-5 text-text-secondary space-y-1">
                      {item.review.map((criterion) => <li key={criterion}>{criterion}</li>)}
                    </ul>
                  </div>
                  <p className="text-text-muted text-xs">Réponse maximale : {item.checks.max_chars} caractères</p>
                  <div className="flex gap-3 pt-2 border-t border-border">
                    <button type="button" onClick={() => setEditing(item)} className="text-xs font-medium text-accent hover:text-accent-strong">Éditer</button>
                    <button type="button" onClick={() => removeCase(item)} className="text-xs font-medium text-error">Supprimer</button>
                  </div>
                </div>
              </details>
            ))}
          </div>
        )}
      </section>

      <section>
        <SectionTitle>Résultats par variante</SectionTitle>
        {metrics.length === 0 ? <EmptyState>Aucun résultat. Lance le benchmark pour comparer les variantes.</EmptyState> : (
          <div className="grid gap-4 lg:grid-cols-2">
            {metrics.map(([variant, value]) => {
              const failures = (report?.outputs?.[variant] ?? []).filter((item) => item.plain_text === false || !item.concise);
              return (
              <Card key={variant} className="space-y-4 lg:col-span-2">
                <p className="font-mono text-xs text-text-primary break-all">{variant}</p>
                <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(260px,0.8fr)]">
                  <div className="grid gap-4 sm:grid-cols-2">
                    <DonutChart passed={legacyCount(value.plain_text_passed, value.plain_text_pct, value.plain_text_total ?? value.n)} total={value.plain_text_total ?? value.n} label="Format texte" />
                    <DonutChart passed={legacyCount(value.concise_passed, value.concise_pct, value.concise_total ?? value.n)} total={value.concise_total ?? value.n} label="Concision" />
                  </div>
                  <aside className="border-t lg:border-t-0 lg:border-l border-border pt-4 lg:pt-0 lg:pl-5">
                    <p className="text-xs uppercase tracking-wide text-text-muted mb-3">Ce qui a échoué ({failures.length})</p>
                    {failures.length === 0 ? (
                      <p className="text-success text-sm">Aucun cas en échec.</p>
                    ) : (
                      <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                        {failures.map((item) => {
                          const reasons = [item.plain_text === false ? "format" : null, !item.concise ? "trop long" : null].filter(Boolean);
                          return (
                            <details key={item.id} className="rounded-md border border-error/20 bg-error-soft px-3 py-2">
                              <summary className="cursor-pointer list-none flex items-center justify-between gap-2 text-sm">
                                <span className="font-mono text-error">{item.id}</span>
                                <span className="text-error text-xs">{reasons.join(" · ")}</span>
                              </summary>
                              <p className="text-text-secondary text-xs mt-2 whitespace-pre-wrap">{item.response || "Réponse vide"}</p>
                            </details>
                          );
                        })}
                      </div>
                    )}
                  </aside>
                </div>
              </Card>
              );
            })}
          </div>
        )}
      </section>

      <section>
        <SectionTitle>Dernier rapport</SectionTitle>
        {report?.stale_reasons.length ? <p role="status" className="text-error text-sm mb-3">Rapport à actualiser : {report.stale_reasons.join(" ")}</p> : null}
        {report ? (
          <Card className="p-0"><pre className="whitespace-pre-wrap text-xs font-mono text-text-secondary p-4 max-h-[560px] overflow-y-auto leading-relaxed">{report.content}</pre></Card>
        ) : <EmptyState>Aucun rapport disponible.</EmptyState>}
      </section>
    </div>
  );
}

function BenchmarkCaseEditor({ initial, onSave, onCancel }: { initial?: BenchmarkCase; onSave: (item: BenchmarkCase) => Promise<void>; onCancel: () => void }) {
  const [id, setId] = useState(initial?.id ?? "");
  const [category, setCategory] = useState(initial?.category ?? "quality");
  const [prompt, setPrompt] = useState(initial?.user ?? "");
  const [maxChars, setMaxChars] = useState(initial?.checks.max_chars ?? 500);
  const [expectJson, setExpectJson] = useState(initial?.checks.expect_json ?? false);
  const [expectPlainText, setExpectPlainText] = useState(initial?.checks.expect_plain_text ?? true);
  const [expectedKeys, setExpectedKeys] = useState(initial?.checks.expect_keys.join(", ") ?? "");
  const [review, setReview] = useState(initial?.review.join("\n") ?? "Réponse correcte, utile et adaptée à la demande");
  const [saving, setSaving] = useState(false);

  const save = async () => {
    const criteria = review.split("\n").map((value) => value.trim()).filter(Boolean);
    if (!id.trim() || !category.trim() || !prompt.trim() || !criteria.length || maxChars < 1) return;
    setSaving(true);
    try {
      await onSave({ id: id.trim(), category: category.trim(), user: prompt.trim(), checks: {
        expect_json: expectJson, expect_keys: expectedKeys.split(",").map((value) => value.trim()).filter(Boolean),
        max_chars: maxChars, expect_plain_text: expectPlainText,
      }, review: criteria });
    } finally { setSaving(false); }
  };

  return <Card className="border-accent/40 mb-4 space-y-4">
    <div className="grid gap-3 sm:grid-cols-2">
      <label className="text-xs text-text-muted">Identifiant<Input value={id} onChange={setId} placeholder="ex. support_refund" className="w-full mt-1" /></label>
      <label className="text-xs text-text-muted">Catégorie<Input value={category} onChange={setCategory} placeholder="quality" className="w-full mt-1" /></label>
    </div>
    <label className="block text-xs text-text-muted">Question envoyée au modèle<Textarea value={prompt} onChange={setPrompt} rows={4} className="mt-1" /></label>
    <div className="grid gap-3 sm:grid-cols-2">
      <label className="text-xs text-text-muted">Longueur maximale<input type="number" min={1} max={100000} value={maxChars} onChange={(e) => setMaxChars(Number(e.target.value))} className="w-full mt-1 bg-bg border border-border rounded-md px-3 py-1.5 text-sm" /></label>
      <label className="text-xs text-text-muted">Clés JSON attendues<Input value={expectedKeys} onChange={setExpectedKeys} placeholder="answer, confidence" className="w-full mt-1" /></label>
    </div>
    <div className="flex flex-wrap gap-5 text-sm text-text-secondary">
      <label className="flex items-center gap-2"><input type="checkbox" checked={expectPlainText} onChange={(e) => setExpectPlainText(e.target.checked)} /> Texte naturel attendu</label>
      <label className="flex items-center gap-2"><input type="checkbox" checked={expectJson} onChange={(e) => setExpectJson(e.target.checked)} /> JSON attendu</label>
    </div>
    <label className="block text-xs text-text-muted">Critères de revue humaine — un par ligne<Textarea value={review} onChange={setReview} rows={3} className="mt-1" /></label>
    <div className="flex justify-end gap-2"><Button onClick={onCancel}>Annuler</Button><Button variant="accent" disabled={saving || !id.trim() || !prompt.trim()} onClick={save}>{saving ? "Enregistrement…" : "Enregistrer"}</Button></div>
  </Card>;
}
