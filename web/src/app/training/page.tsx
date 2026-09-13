"use client";

import { ReactNode, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, JobStatus, ModelPreflight, Project, TrainingConfigSummary, TrainingMetricPoint } from "@/lib/api";
import { Button, Card, EmptyState, Input, PageHeader, Pill, SectionTitle, StatusBadge } from "@/components/ui";
import { LineChart } from "@/components/line-chart";
import { useProject } from "@/lib/project-context";
import { ModelPreflightCard } from "@/components/model-preflight-card";

export default function TrainingPage() {
  const { projectId, project } = useProject();
  return projectId ? <ProjectTraining key={projectId} projectId={projectId} project={project} /> : <p>Sélectionne un projet.</p>;
}

function ProjectTraining({ projectId, project }: { projectId: string; project: Project | null }) {
  const [configs, setConfigs] = useState<TrainingConfigSummary[]>([]);
  const [jobs, setJobs] = useState<JobStatus[]>([]);
  const [selectedJob, setSelectedJob] = useState<string | null>(null);
  const [pipelineConfig, setPipelineConfig] = useState<string>("");
  const [pipelineVersion, setPipelineVersion] = useState("");
  const [pipelineResume, setPipelineResume] = useState(false);
  const [sweepVersion, setSweepVersion] = useState("");
  const [sweepResume, setSweepResume] = useState(false);
  const [metricResult, setMetricResult] = useState<{ jobId: string; points: TrainingMetricPoint[] } | null>(null);
  const initialized = useRef(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [newConfigOpen, setNewConfigOpen] = useState(false);
  const [newConfigName, setNewConfigName] = useState("");
  const [newConfigNotes, setNewConfigNotes] = useState("");
  const [newConfigDatasetVersion, setNewConfigDatasetVersion] = useState("");
  const [newConfigR, setNewConfigR] = useState(16);
  const [newConfigAlpha, setNewConfigAlpha] = useState<number | "">("");
  const [newConfigDropout, setNewConfigDropout] = useState(0.05);
  const [newConfigEpochs, setNewConfigEpochs] = useState(2);
  const [newConfigLr, setNewConfigLr] = useState(0.0002);
  const [newConfigBatchSize, setNewConfigBatchSize] = useState(1);
  const [newConfigGradAccum, setNewConfigGradAccum] = useState(8);
  const [newConfigWarmup, setNewConfigWarmup] = useState(5);
  const [newConfigError, setNewConfigError] = useState<string | null>(null);
  const [preflight, setPreflight] = useState<ModelPreflight | null>(null);
  const [preflightLoading, setPreflightLoading] = useState(true);

  const checkModel = () => {
    if (!project?.base_model) return;
    setPreflightLoading(true);
    api.training.preflight(projectId, project.base_model)
      .then(setPreflight)
      .catch(() => setPreflight(null))
      .finally(() => setPreflightLoading(false));
  };

  const refresh = () => {
    if (!projectId) return;
    api.training.configs(projectId).then((next) => {
      setConfigs(next);
      if (!initialized.current && next.length) {
        initialized.current = true;
        setPipelineConfig(next[0].filename);
        setPipelineVersion(suggestNextVersion(next[0].dataset_version));
        setSweepVersion(suggestNextVersion(next[0].dataset_version));
      }
    });
    api.jobs.list(projectId).then(setJobs);
  };

  useEffect(() => {
    refresh();
    if (!projectId) return;
    pollRef.current = setInterval(refresh, 3000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!project?.base_model) return;
    api.training.preflight(projectId, project.base_model)
      .then(setPreflight)
      .catch(() => setPreflight(null))
      .finally(() => setPreflightLoading(false));
  }, [projectId, project?.base_model]);

  const startTraining = async (filename: string) => {
    if (!projectId) return;
    const job = await api.training.start(projectId, filename);
    setSelectedJob(job.job_id);
    refresh();
  };

  const runPipeline = async () => {
    if (!pipelineConfig || !pipelineVersion.trim() || !projectId) return;
    const job = await api.training.pipeline(projectId, pipelineConfig, pipelineVersion.trim(), pipelineResume);
    setSelectedJob(job.job_id);
    refresh();
  };

  const runSweep = async () => {
    if (!sweepVersion.trim() || !projectId) return;
    const job = await api.training.sweep(projectId, sweepVersion.trim(), sweepResume);
    setSelectedJob(job.job_id);
    refresh();
  };

  const createConfig = async () => {
    setNewConfigError(null);
    if (!newConfigName.trim() || !newConfigDatasetVersion.trim() || !projectId) return;
    try {
      await api.training.createConfig(projectId, {
        name: newConfigName.trim(),
        notes: newConfigNotes.trim() || undefined,
        dataset_version: newConfigDatasetVersion.trim(),
        lora_r: newConfigR,
        lora_alpha: newConfigAlpha === "" ? undefined : newConfigAlpha,
        lora_dropout: newConfigDropout,
        epochs: newConfigEpochs,
        learning_rate: newConfigLr,
        batch_size: newConfigBatchSize,
        gradient_accumulation_steps: newConfigGradAccum,
        warmup_steps: newConfigWarmup,
      });
      setNewConfigName("");
      setNewConfigNotes("");
      setNewConfigOpen(false);
      refresh();
    } catch (e) {
      setNewConfigError(String(e));
    }
  };

  const selectedConfigHasResult = configs.find((c) => c.filename === pipelineConfig)?.has_result ?? false;

  const activeJob = jobs.find((j) => j.job_id === selectedJob) ?? jobs[0];
  const metrics = metricResult?.jobId === activeJob?.job_id ? metricResult?.points ?? [] : [];

  useEffect(() => {
    const kindsWithMetrics: string[] = ["training", "pipeline"];
    if (!activeJob || !kindsWithMetrics.includes(activeJob.kind)) {
      return;
    }
    let active = true;
    const loadMetrics = () => api.jobs.metrics(activeJob.job_id).then((points) => {
      if (active) setMetricResult({ jobId: activeJob.job_id, points });
    }).catch(() => {});
    loadMetrics();
    const interval = activeJob.status === "running" ? setInterval(loadMetrics, 3000) : null;
    return () => { active = false; if (interval) clearInterval(interval); };
  }, [activeJob?.job_id, activeJob?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-10">
      <PageHeader
        title="Training"
        description="Chaque entraînement réussi est suivi d'une évaluation automatique. Les jobs terminés sont conservés après redémarrage."
      />
      <ModelPreflightCard result={preflight} loading={preflightLoading} onRetry={checkModel} />

      <section>
        <SectionTitle>Pipeline automatique</SectionTitle>
        <Card className="space-y-3">
          <p className="text-text-secondary text-sm">
            Enchaîne automatiquement <span className="font-mono text-text-primary">valider → reconstruire les splits → entraîner → évaluer</span>,
            en un seul job de fond — s&apos;arrête tout seul si la validation échoue, ne lance jamais un entraînement sur un dataset cassé.
            Porte uniquement sur <span className="font-mono text-text-primary">datasets/</span> (comportement) — jamais sur les documents RAG.
          </p>
          <div className="flex items-center gap-2 flex-wrap">
            <select
              value={pipelineConfig}
              onChange={(e) => setPipelineConfig(e.target.value)}
              className="bg-bg border border-border rounded-md px-3 py-1.5 text-sm text-text-primary focus:outline-none focus:border-accent transition-colors"
            >
              {configs.map((cfg) => (
                <option key={cfg.filename} value={cfg.filename}>
                  {cfg.filename} (r={cfg.lora_r})
                </option>
              ))}
            </select>
            <Input value={pipelineVersion} onChange={setPipelineVersion} placeholder="dataset-v0.4" className="w-40" />
            <label className="flex items-center gap-1.5 text-sm text-text-secondary cursor-pointer select-none">
              <input type="checkbox" checked={pipelineResume} onChange={(e) => setPipelineResume(e.target.checked)} className="accent-[var(--accent)]" />
              Reprendre/écraser
            </label>
            <Button variant="accent" onClick={runPipeline} disabled={!preflight?.ready || !pipelineConfig || !pipelineVersion.trim()}>
              Lancer le pipeline complet
            </Button>
          </div>
          {selectedConfigHasResult && !pipelineResume && (
            <p className="text-accent text-xs">
              Cette config a déjà un résultat (adapter existant) — le training échouera à l&apos;étape train sans
              cocher &quot;Reprendre/écraser&quot;, ou change de config.
            </p>
          )}
        </Card>
      </section>

      <section>
        <SectionTitle>Sweep complet (r=8/16/32)</SectionTitle>
        <Card className="space-y-3">
          <p className="text-text-secondary text-sm">
            Enchaîne le pipeline complet pour les 3 rangs LoRA d&apos;affilée, un seul job — comparaison complète en un
            clic. Continue même si un des trois échoue (tu récupères quand même les autres résultats).
          </p>
          <div className="flex items-center gap-2 flex-wrap">
            <Input value={sweepVersion} onChange={setSweepVersion} placeholder="dataset-v0.4" className="w-40" />
            <label className="flex items-center gap-1.5 text-sm text-text-secondary cursor-pointer select-none">
              <input type="checkbox" checked={sweepResume} onChange={(e) => setSweepResume(e.target.checked)} className="accent-[var(--accent)]" />
              Reprendre/écraser
            </label>
            <Button variant="accent" onClick={runSweep} disabled={!preflight?.ready || !sweepVersion.trim()}>
              Lancer le sweep complet
            </Button>
          </div>
        </Card>
      </section>

      <section>
        <div className="flex items-center justify-between mb-3">
          <SectionTitle>Nouvelle config</SectionTitle>
          <Button variant="ghost" onClick={() => setNewConfigOpen((v) => !v)}>
            {newConfigOpen ? "Fermer" : "+ Créer une config"}
          </Button>
        </div>
        {newConfigOpen && (
          <Card className="space-y-3">
            <p className="text-text-secondary text-sm">
              Génère un fichier <span className="font-mono text-text-primary">training/configs/custom_&lt;nom&gt;.yaml</span> avec
              ces hyperparamètres, sans éditer de YAML à la main. Modèle de base = celui du projet actif (
              <span className="font-mono text-text-primary">{project?.base_model ?? "—"}</span>). Modules cibles LoRA et
              quantization 4-bit repris tels quels des configs existantes.
            </p>
            {newConfigError && <p className="text-error text-sm">{newConfigError}</p>}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <Field label="Nom">
                <Input value={newConfigName} onChange={setNewConfigName} placeholder="r24_test" />
              </Field>
              <Field label="Version dataset">
                <Input value={newConfigDatasetVersion} onChange={setNewConfigDatasetVersion} placeholder="dataset-v0.4" />
              </Field>
              <Field label="LoRA r">
                <NumberInput value={newConfigR} onChange={(v) => setNewConfigR(v === "" ? 0 : v)} />
              </Field>
              <Field label="LoRA alpha (auto = 2r)">
                <NumberInput value={newConfigAlpha} onChange={setNewConfigAlpha} placeholder="auto" />
              </Field>
              <Field label="Dropout">
                <NumberInput value={newConfigDropout} onChange={(v) => setNewConfigDropout(v === "" ? 0 : v)} step={0.01} />
              </Field>
              <Field label="Epochs">
                <NumberInput value={newConfigEpochs} onChange={(v) => setNewConfigEpochs(v === "" ? 0 : v)} />
              </Field>
              <Field label="Learning rate">
                <NumberInput value={newConfigLr} onChange={(v) => setNewConfigLr(v === "" ? 0 : v)} step={0.00001} />
              </Field>
              <Field label="Batch size">
                <NumberInput value={newConfigBatchSize} onChange={(v) => setNewConfigBatchSize(v === "" ? 0 : v)} />
              </Field>
              <Field label="Grad. accumulation">
                <NumberInput value={newConfigGradAccum} onChange={(v) => setNewConfigGradAccum(v === "" ? 0 : v)} />
              </Field>
              <Field label="Warmup steps">
                <NumberInput value={newConfigWarmup} onChange={(v) => setNewConfigWarmup(v === "" ? 0 : v)} />
              </Field>
            </div>
            <Input value={newConfigNotes} onChange={setNewConfigNotes} placeholder="Notes (optionnel)" />
            <Button
              variant="accent"
              onClick={createConfig}
              disabled={!newConfigName.trim() || !newConfigDatasetVersion.trim()}
            >
              Créer la config
            </Button>
          </Card>
        )}
      </section>

      <section>
        <SectionTitle>Configs disponibles</SectionTitle>
        <Card className="mb-4 text-sm text-text-secondary leading-relaxed">
          <span className="text-text-primary font-medium">r</span> = rang LoRA, la capacité de l&apos;adaptateur.
          Plus haut = plus de paramètres entraînables = plus de nuance possible, mais adapter plus lourd sur disque
          (VRAM d&apos;entraînement quasi identique sur ce modèle 1B). Sur nos essais (dataset-v0.3) :{" "}
          <span className="font-mono text-text-primary">r=8</span> sous-capacité (JSON invalide la plupart du temps),{" "}
          <span className="font-mono text-text-primary">r=16</span> intermédiaire,{" "}
          <span className="font-mono text-accent">r=32</span> meilleur résultat (100% JSON valide, eval loss le plus
          bas) — voir <Link href="/" className="text-accent hover:underline">le dashboard</Link>.
        </Card>
        <div className="grid gap-4 sm:grid-cols-3">
          {configs.map((cfg) => (
            <Card key={cfg.filename} className="space-y-3">
              <div>
                <p className="font-mono text-sm text-text-primary">{cfg.filename}</p>
                <p className="text-text-muted text-xs mt-1 leading-relaxed">{cfg.notes}</p>
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <Pill>{cfg.base_model.split("/").pop()}</Pill>
                <Pill>r={cfg.lora_r}</Pill>
                <Pill>{cfg.dataset_version}</Pill>
                {cfg.has_result && <span className="text-success text-xs font-medium">✓ résultat</span>}
              </div>
              <Button onClick={() => startTraining(cfg.filename)} disabled={!preflight?.ready} className="w-full">
                Lancer
              </Button>
            </Card>
          ))}
        </div>
      </section>

      <section>
        <SectionTitle>Jobs</SectionTitle>
        <div className="grid grid-cols-[280px_1fr] gap-4">
          <div className="space-y-1">
            {jobs.length === 0 && <EmptyState>Aucun job pour l&apos;instant.</EmptyState>}
            {jobs.map((j) => (
              <button
                key={j.job_id}
                onClick={() => setSelectedJob(j.job_id)}
                className={`w-full text-left px-3 py-2.5 rounded-md text-sm transition-colors ${
                  activeJob?.job_id === j.job_id ? "bg-accent-soft" : "hover:bg-surface-hover"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono text-text-primary">{j.job_id}</span>
                  <StatusBadge status={j.status} />
                </div>
                <div className="text-xs text-text-muted mt-0.5">
                  {j.kind}
                  {j.config_filename && ` · ${j.config_filename}`}
                </div>
              </button>
            ))}
          </div>

          <div>
            {activeJob ? (
              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  <span className="font-mono text-sm text-text-primary">{activeJob.job_id}</span>
                  <StatusBadge status={activeJob.status} />
                  {activeJob.status === "running" && (
                    <button
                      onClick={() => api.jobs.stop(activeJob.job_id).then(refresh)}
                      className="text-error/80 hover:text-error text-xs font-medium transition-colors ml-auto"
                    >
                      Arrêter
                    </button>
                  )}
                </div>
                {activeJob.status === "failed" && activeJob.error_message ? (
                  <Card className="border-error/30 bg-error-soft text-sm">
                    <p className="text-error font-medium">{activeJob.error_message}</p>
                    {activeJob.suggestion ? <p className="text-text-secondary mt-1">{activeJob.suggestion}</p> : null}
                  </Card>
                ) : null}
                {metrics.length > 0 && (
                  <Card>
                    <p className="text-text-muted text-xs uppercase tracking-wide mb-3">Loss en direct</p>
                    <LineChart
                      series={[
                        {
                          label: "train loss",
                          color: "var(--accent)",
                          points: metrics.filter((m) => m.loss != null).map((m) => ({ x: m.step, y: m.loss as number })),
                        },
                        {
                          label: "eval loss",
                          color: "var(--info)",
                          points: metrics.filter((m) => m.eval_loss != null).map((m) => ({ x: m.step, y: m.eval_loss as number })),
                        },
                      ]}
                    />
                  </Card>
                )}
                <Card className="p-0">
                  <pre className="text-xs font-mono text-text-secondary p-4 whitespace-pre-wrap max-h-[420px] overflow-y-auto leading-relaxed">
                    {activeJob.log_tail.join("\n") || "(pas encore de sortie)"}
                  </pre>
                </Card>
                {activeJob.result && (
                  <Card className="p-0">
                    <pre className="text-xs font-mono text-accent-strong p-4 whitespace-pre-wrap leading-relaxed">
                      {JSON.stringify(activeJob.result, null, 2)}
                    </pre>
                  </Card>
                )}
              </div>
            ) : (
              <EmptyState>Sélectionne un job à gauche.</EmptyState>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-xs text-text-muted">
      {label}
      {children}
    </label>
  );
}

function NumberInput({
  value,
  onChange,
  step,
  placeholder,
}: {
  value: number | "";
  onChange: (v: number | "") => void;
  step?: number;
  placeholder?: string;
}) {
  return (
    <input
      type="number"
      value={value}
      step={step}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))}
      className="bg-bg border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary focus:outline-none focus:border-accent transition-colors"
    />
  );
}

function suggestNextVersion(current: string): string {
  const match = current.match(/^(.*-v)(\d+)\.(\d+)$/);
  if (!match) return current;
  const [, prefix, major, minor] = match;
  return `${prefix}${major}.${parseInt(minor, 10) + 1}`;
}
