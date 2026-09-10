"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, CurrentDatasetVersion, DatasetCategorySummary, DatasetStats, EvalSummaryMetric, EvaluationReport, ExperimentResult, JobStatus, RagDocument } from "@/lib/api";
import { Button, Card, EmptyState, PageHeader, Pill, SectionTitle, StatusBadge } from "@/components/ui";
import { BarChart } from "@/components/bar-chart";
import { useProject } from "@/lib/project-context";

const RAG_CATEGORY_LABELS: Record<string, string> = {
  methods: "Méthodes",
  research: "Études",
  product: "Produit",
  other: "Autre",
};

export default function DashboardPage() {
  const { projectId } = useProject();
  return projectId ? <ProjectDashboard key={projectId} projectId={projectId} /> : <p>Sélectionne un projet.</p>;
}

function ProjectDashboard({ projectId }: { projectId: string }) {
  const [experiments, setExperiments] = useState<ExperimentResult[] | null>(null);
  const [report, setReport] = useState<string | null>(null);
  const [reportInfo, setReportInfo] = useState<EvaluationReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [datasetStats, setDatasetStats] = useState<DatasetStats | null>(null);
  const [datasetCategories, setDatasetCategories] = useState<DatasetCategorySummary[] | null>(null);
  const [ragDocuments, setRagDocuments] = useState<RagDocument[] | null>(null);
  const [jobs, setJobs] = useState<JobStatus[]>([]);
  const [evalSummary, setEvalSummary] = useState<Record<string, EvalSummaryMetric> | null>(null);
  const [currentVersion, setCurrentVersion] = useState<CurrentDatasetVersion | null>(null);
  const [trainingBusy, setTrainingBusy] = useState(false);
  const [trainingError, setTrainingError] = useState<string | null>(null);
  const [deploymentOpen, setDeploymentOpen] = useState(false);
  const hadRunningJobs = useRef(false);

  const refreshData = useCallback(() => {
    api.experiments
      .list(projectId)
      .then((items) => { setExperiments(items); setError(null); })
      .catch((e) => setError(String(e)));
    api.experiments
      .report(projectId)
      .then((r) => { setReport(r.content); setReportInfo(r); })
      .catch(() => { setReport(null); setReportInfo(null); });
    api.dataset.stats(projectId).then(setDatasetStats).catch(() => {});
    api.dataset.categories(projectId).then(setDatasetCategories).catch(() => {});
    api.rag.documents(projectId).then(setRagDocuments).catch(() => {});
    api.dataset.currentVersion(projectId).then(setCurrentVersion).catch(() => {});
    api.experiments.reportSummary(projectId).then(setEvalSummary).catch(() => setEvalSummary(null));
  }, [projectId]);

  const refreshJobs = useCallback(() => {
    api.jobs.list(projectId).then((items) => {
      const recent = items.slice(0, 5);
      const hasRunningJobs = recent.some((job) => job.status === "running");
      setJobs(recent);
      if (hadRunningJobs.current && !hasRunningJobs) refreshData();
      hadRunningJobs.current = hasRunningJobs;
    }).catch(() => {});
  }, [projectId, refreshData]);

  const refreshAll = useCallback(() => {
    refreshData();
    refreshJobs();
  }, [refreshData, refreshJobs]);

  useEffect(() => {
    refreshAll();
    const interval = setInterval(refreshJobs, 5000);
    window.addEventListener("focus", refreshAll);
    return () => {
      clearInterval(interval);
      window.removeEventListener("focus", refreshAll);
    };
  }, [refreshAll, refreshJobs]);

  const trainCurrentVersion = async () => {
    if (!currentVersion?.version || !projectId) return;
    setTrainingBusy(true);
    setTrainingError(null);
    try {
      await api.training.sweep(projectId, currentVersion.version, true);
      refreshAll();
    } catch (e) {
      setTrainingError(String(e));
    } finally {
      setTrainingBusy(false);
    }
  };

  const best = experiments?.reduce<ExperimentResult | null>((acc, e) => {
    if (e.eval_loss == null) return acc;
    if (!acc || (acc.eval_loss ?? Infinity) > e.eval_loss) return e;
    return acc;
  }, null);

  const ragByCategory = new Map<string, number>();
  for (const doc of ragDocuments ?? []) {
    ragByCategory.set(doc.category, (ragByCategory.get(doc.category) ?? 0) + 1);
  }

  const runningJobs = jobs.filter((j) => j.status === "running").length;
  const deploymentReady = (experiments?.length ?? 0) > 0 || (ragDocuments?.length ?? 0) > 0;

  return (
    <div className="space-y-10">
      <PageHeader
        title="Dashboard"
        description="Vue d'ensemble du dataset, du RAG, des expériences et des jobs en cours."
        action={
          <div title={deploymentReady ? "Préparer le projet pour un runtime local" : "Ajoute un RAG ou entraîne un modèle pour activer le déploiement"}>
            <Button variant="accent" onClick={() => setDeploymentOpen((open) => !open)} disabled={!deploymentReady}>
              Déployer vers Ollama / vLLM
            </Button>
          </div>
        }
      />

      {deploymentOpen && (
        <Card className="flex items-start justify-between gap-4 border-accent/40">
          <div>
            <p className="font-display text-text-primary">Déploiement du projet</p>
            <p className="text-text-secondary text-sm mt-1">
              Point d’entrée pour ajouter le modèle à Ollama, vLLM ou un autre runtime après entraînement ou indexation du RAG.
            </p>
          </div>
          <Button variant="ghost" onClick={() => setDeploymentOpen(false)}>Fermer</Button>
        </Card>
      )}

      {error && (
        <Card className="border-error/30 bg-error-soft text-error text-sm">
          {error} — le backend FastAPI tourne-t-il sur :8000 ?
        </Card>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card>
          <p className="text-text-muted text-xs uppercase tracking-wide mb-1">Exemples dataset</p>
          <p className="font-display text-3xl text-text-primary">{datasetStats?.total_examples ?? "—"}</p>
          <p className="text-text-muted text-xs mt-1">{datasetStats ? `${datasetStats.exact_duplicates} doublon(s) exact(s)` : "\u00a0"}</p>
        </Card>
        <Card>
          <p className="text-text-muted text-xs uppercase tracking-wide mb-1">Documents RAG</p>
          <p className="font-display text-3xl text-text-primary">{ragDocuments?.length ?? "—"}</p>
          <p className="text-text-muted text-xs mt-1">{ragByCategory.size} catégorie(s)</p>
        </Card>
        <Card>
          <p className="text-text-muted text-xs uppercase tracking-wide mb-1">Meilleur eval loss</p>
          <p className="font-display text-3xl text-accent">{best?.eval_loss?.toFixed(3) ?? "—"}</p>
          {best && <p className="text-text-muted text-xs mt-1 font-mono">{best.experiment_id}</p>}
        </Card>
        <Card>
          <p className="text-text-muted text-xs uppercase tracking-wide mb-1">Jobs en cours</p>
          <p className={`font-display text-3xl ${runningJobs > 0 ? "text-info" : "text-text-primary"}`}>{runningJobs}</p>
          <p className="text-text-muted text-xs mt-1">{jobs.length} récent(s)</p>
        </Card>
      </div>

      <div className="grid sm:grid-cols-2 gap-6">
        <section>
          <SectionTitle>Dataset par catégorie</SectionTitle>
          <Card className="space-y-2">
            {!datasetCategories ? (
              <p className="text-text-muted text-sm">Chargement…</p>
            ) : datasetCategories.length === 0 ? (
              <EmptyState>Aucun exemple pour l&apos;instant.</EmptyState>
            ) : (
              datasetCategories.map((cat) => (
                <div key={cat.category} className="flex items-center justify-between text-sm">
                  <span className="text-text-secondary">{cat.category}</span>
                  <span className="font-mono text-text-primary">{cat.example_count}</span>
                </div>
              ))
            )}
            <Link href="/dataset" className="block text-accent text-xs pt-1 hover:underline">
              Gérer le dataset →
            </Link>
          </Card>
        </section>

        <section>
          <SectionTitle>RAG par catégorie</SectionTitle>
          <Card className="space-y-2">
            {!ragDocuments ? (
              <p className="text-text-muted text-sm">Chargement…</p>
            ) : ragDocuments.length === 0 ? (
              <EmptyState>Aucun document pour l&apos;instant.</EmptyState>
            ) : (
              Array.from(ragByCategory.entries()).map(([cat, count]) => (
                <div key={cat} className="flex items-center justify-between text-sm">
                  <span className="text-text-secondary">{RAG_CATEGORY_LABELS[cat] ?? cat}</span>
                  <span className="font-mono text-text-primary">{count}</span>
                </div>
              ))
            )}
            <Link href="/rag" className="block text-accent text-xs pt-1 hover:underline">
              Gérer le RAG →
            </Link>
          </Card>
        </section>
      </div>

      <section>
        <SectionTitle>Jobs récents</SectionTitle>
        {jobs.length === 0 ? (
          <EmptyState>Aucun job pour l&apos;instant.</EmptyState>
        ) : (
          <Card className="p-0 overflow-hidden">
            {jobs.map((j) => (
              <div key={j.job_id} className="flex items-center justify-between px-4 py-2.5 border-b border-border last:border-0 text-sm">
                <div className="flex items-center gap-3">
                  <span className="font-mono text-text-primary">{j.job_id}</span>
                  <Pill>{j.kind}</Pill>
                  {j.config_filename && <span className="text-text-muted text-xs font-mono">{j.config_filename}</span>}
                </div>
                <StatusBadge status={j.status} />
              </div>
            ))}
            <Link href="/training" className="block text-accent text-xs px-4 py-2.5 hover:underline">
              Voir tous les jobs →
            </Link>
          </Card>
        )}
      </section>

      <section>
        <SectionTitle>Expériences</SectionTitle>
        {!experiments ? (
          <p className="text-text-muted text-sm">Chargement…</p>
        ) : experiments.length === 0 ? (
          <EmptyState>Aucune expérience pour l&apos;instant. Lance un training depuis l&apos;onglet Training.</EmptyState>
        ) : (
          <Card className="p-0 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-text-muted text-xs uppercase tracking-wide">
                    <th className="text-left px-4 py-2.5 font-medium">ID</th>
                    <th className="text-left px-4 py-2.5 font-medium">Modèle</th>
                    <th className="text-left px-4 py-2.5 font-medium">r</th>
                    <th className="text-left px-4 py-2.5 font-medium">Dataset</th>
                    <th className="text-right px-4 py-2.5 font-medium">Train loss</th>
                    <th className="text-right px-4 py-2.5 font-medium">Eval loss</th>
                    <th className="text-right px-4 py-2.5 font-medium">Durée</th>
                    <th className="text-right px-4 py-2.5 font-medium">VRAM</th>
                    <th className="text-right px-4 py-2.5 font-medium">Adapter</th>
                  </tr>
                </thead>
                <tbody>
                  {experiments.map((exp) => (
                    <tr key={exp.experiment_id} className="border-b border-border last:border-0 hover:bg-surface-hover transition-colors">
                      <td className="px-4 py-2.5 font-mono text-text-primary">{exp.experiment_id}</td>
                      <td className="px-4 py-2.5 font-mono text-text-secondary">{exp.base_model?.split("/").pop() ?? "—"}</td>
                      <td className="px-4 py-2.5 font-mono text-text-secondary">{exp.lora?.r ?? "—"}</td>
                      <td className="px-4 py-2.5 text-text-secondary">{exp.dataset_version ?? "—"}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-text-secondary">{exp.train_loss?.toFixed(3) ?? "—"}</td>
                      <td className={`px-4 py-2.5 text-right font-mono ${exp.experiment_id === best?.experiment_id ? "text-accent" : "text-text-secondary"}`}>
                        {exp.eval_loss?.toFixed(3) ?? "—"}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono text-text-secondary">{exp.train_duration_minutes ?? "—"} min</td>
                      <td className="px-4 py-2.5 text-right font-mono text-text-secondary">{exp.peak_vram_mb ? `${(exp.peak_vram_mb / 1024).toFixed(1)} GB` : "—"}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-text-secondary">{exp.adapter_size_mb ? `${exp.adapter_size_mb} MB` : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        )}
      </section>

      {experiments && experiments.length > 0 && (
        <div className="grid sm:grid-cols-2 gap-6">
          <section>
            <SectionTitle>Eval loss par expérience</SectionTitle>
            <Card>
              <p className="text-text-muted text-xs mb-3">
                Plus bas = mieux. Meilleur en surbrillance. <span className="text-text-secondary">r</span> = rang LoRA
                (capacité de l&apos;adaptateur) — <Link href="/training" className="text-accent hover:underline">détails</Link>.
              </p>
              <BarChart
                data={experiments
                  .filter((e) => e.eval_loss != null)
                  .map((e) => ({
                    label: `${e.experiment_id} (r=${e.lora?.r ?? "?"})`,
                    value: e.eval_loss as number,
                    highlight: e.experiment_id === best?.experiment_id,
                  }))}
                formatValue={(v) => v.toFixed(3)}
              />
            </Card>
          </section>

          <section>
            <SectionTitle>Taille des adapters</SectionTitle>
            <Card>
              <p className="text-text-muted text-xs mb-3">Poids LoRA sauvegardés sur disque, par rang.</p>
              <BarChart
                data={experiments
                  .filter((e) => e.adapter_size_mb != null)
                  .map((e) => ({
                    label: `${e.experiment_id} (r=${e.lora?.r ?? "?"})`,
                    value: e.adapter_size_mb as number,
                  }))}
                formatValue={(v) => v.toFixed(1)}
                unit=" MB"
              />
            </Card>
          </section>
        </div>
      )}

      {(currentVersion?.version || (experiments && experiments.length > 0)) && (
        <section>
          <div className="flex items-center justify-between gap-4 mb-3 flex-wrap">
            <SectionTitle>Historique des versions du dataset</SectionTitle>
            {currentVersion?.version && (
              <Button variant="accent" onClick={trainCurrentVersion} disabled={trainingBusy}>
                Entraîner {currentVersion.version} (sweep r=8/16/32)
              </Button>
            )}
          </div>
          <p className="text-text-muted text-xs mb-3">
            La version « actuelle » vient de <span className="font-mono text-text-primary">data/VERSION</span> (dernier
            &quot;Reconstruire&quot; sur <Link href="/dataset" className="text-accent hover:underline">/dataset</Link>) —
            elle peut ne pas encore avoir été utilisée par un training. Le bouton lance le pipeline complet (valider →
            splits → entraîner) pour r=8/16/32 sur la version actuelle, un seul job de fond suivi dans{" "}
            <Link href="/training" className="text-accent hover:underline">Training</Link>.
          </p>
          {trainingError && <Card className="border-error/30 bg-error-soft text-error text-sm mb-3">{trainingError}</Card>}
          <Card className="p-0 overflow-hidden">
            {(() => {
              const versionMap = (experiments ?? []).reduce((map, e) => {
                const v = e.dataset_version ?? "inconnue";
                if (!map.has(v)) map.set(v, []);
                map.get(v)!.push(e.experiment_id);
                return map;
              }, new Map<string, string[]>());

              const rows: { version: string; ids: string[]; isCurrent: boolean }[] = [];
              if (currentVersion?.version) {
                rows.push({ version: currentVersion.version, ids: versionMap.get(currentVersion.version) ?? [], isCurrent: true });
                versionMap.delete(currentVersion.version);
              }
              for (const [version, ids] of versionMap) rows.push({ version, ids, isCurrent: false });

              return rows.map(({ version, ids, isCurrent }) => (
                <div key={version} className="flex items-center justify-between px-4 py-2.5 border-b border-border last:border-0 text-sm">
                  <div className="flex items-center gap-2">
                    <span className={`font-mono ${isCurrent ? "text-accent" : "text-text-primary"}`}>{version}</span>
                    {isCurrent && <span className="text-accent text-xs">● actuelle</span>}
                  </div>
                  <span className="text-text-muted text-xs">{ids.length > 0 ? ids.join(", ") : "pas encore entraînée"}</span>
                </div>
              ));
            })()}
          </Card>
        </section>
      )}

      {evalSummary && Object.keys(evalSummary).length > 0 && (
        <section>
          <SectionTitle>Qualité par variante (benchmark comportemental)</SectionTitle>
          <p className="text-text-muted text-xs mb-3">
            Variantes évaluées sur {Object.values(evalSummary)[0]?.n ?? 0} prompts. Ces contrôles mesurent le format,
            la concision et les signaux de refus ; la pertinence des actions reste à vérifier dans les réponses.
          </p>
          {reportInfo?.stale_reasons.length ? (
            <p role="status" className="text-error text-sm mb-3">Rapport à actualiser : {reportInfo.stale_reasons.join(" ")}</p>
          ) : null}
          <div className="grid sm:grid-cols-3 gap-6">
            <Card>
              <p className="text-text-muted text-xs uppercase tracking-wide mb-3">Format texte</p>
              <BarChart
                data={Object.entries(evalSummary)
                  .filter(([, m]) => m.plain_text_pct != null)
                  .map(([label, m]) => ({ label, value: m.plain_text_pct as number }))}
                formatValue={(v) => v.toFixed(0)}
                unit="%"
              />
            </Card>
            <Card>
              <p className="text-text-muted text-xs uppercase tracking-wide mb-3">Concision</p>
              <BarChart
                data={Object.entries(evalSummary)
                  .filter(([, m]) => m.concise_pct != null)
                  .map(([label, m]) => ({ label, value: m.concise_pct as number }))}
                formatValue={(v) => v.toFixed(0)}
                unit="%"
              />
            </Card>
            <Card>
              <p className="text-text-muted text-xs uppercase tracking-wide mb-3">Safety pass</p>
              <BarChart
                data={Object.entries(evalSummary)
                  .filter(([, m]) => m.safety_pass_pct != null)
                  .map(([label, m]) => ({ label, value: m.safety_pass_pct as number }))}
                formatValue={(v) => v.toFixed(0)}
                unit="%"
              />
            </Card>
          </div>
        </section>
      )}

      <section>
        <SectionTitle>Dernier rapport d&apos;évaluation</SectionTitle>
        {reportInfo?.metadata.generated_at && (
          <p className="text-text-muted text-xs mb-3">
            {new Date(reportInfo.metadata.generated_at).toLocaleString("fr-FR")} · Dataset {reportInfo.metadata.dataset_version ?? "inconnu"}
          </p>
        )}
        {reportInfo?.comparison?.comparable && (
          <div className="text-sm text-text-secondary mb-3 space-y-1">
            <p>Écart avec le rapport précédent, en points de pourcentage :</p>
            {Object.entries(reportInfo.comparison.deltas).map(([label, metrics]) => (
              <p key={label}>{label} : {Object.entries(metrics).filter(([key]) =>
                ["plain_text_pct", "concise_pct", "safety_pass_pct"].includes(key)).map(([key, value]) =>
                `${({ plain_text_pct: "format texte", concise_pct: "concision", safety_pass_pct: "refus" } as Record<string, string>)[key]} ${value > 0 ? "+" : ""}${value}`
              ).join(" ; ")}</p>
            ))}
          </div>
        )}
        {report ? (
          <Card className="p-0">
            <pre className="whitespace-pre-wrap text-xs font-mono text-text-secondary p-4 max-h-[500px] overflow-y-auto leading-relaxed">
              {report}
            </pre>
          </Card>
        ) : (
          <EmptyState>Aucun rapport pour l&apos;instant. Lance une évaluation depuis l&apos;onglet Training.</EmptyState>
        )}
      </section>
    </div>
  );
}
