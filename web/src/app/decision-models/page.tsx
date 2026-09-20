"use client";

import { useEffect, useState } from "react";
import { api, DecisionDatasetStats, DecisionEvaluationResult, DecisionSchema } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import { useAction } from "@/lib/use-action";
import { Button, Card, EmptyState, Field, Input, PageHeader, SectionTitle, Skeleton, Textarea } from "@/components/ui";
import { ConfusionMatrix } from "@/components/confusion-matrix";

export default function DecisionModelsPage() {
  const { projectId } = useProject();
  const [schema, setSchema] = useState<DecisionSchema | null | undefined>(undefined);
  const [stats, setStats] = useState<DecisionDatasetStats | null>(null);
  const [evaluation, setEvaluation] = useState<DecisionEvaluationResult | null>(null);

  const [name, setName] = useState("");
  const [decisionsText, setDecisionsText] = useState("");
  const [exampleInput, setExampleInput] = useState("");
  const [exampleDecision, setExampleDecision] = useState("");
  const [inferInput, setInferInput] = useState("");
  const [inferResult, setInferResult] = useState<{ decision: string; confidence: number | null } | null>(null);

  const load = () => {
    if (!projectId) return;
    api.decisionModels.getSchema(projectId).then((s) => {
      setSchema(s);
      if (s) setDecisionsText(s.decisions.join(", "));
      setName(s?.name ?? "");
    });
    api.decisionModels.stats(projectId).then(setStats).catch(() => setStats(null));
  };

  useEffect(load, [projectId]);

  const saveSchema = useAction(async () => {
    if (!projectId) return;
    const decisions = decisionsText.split(",").map((d) => d.trim()).filter(Boolean);
    const saved = await api.decisionModels.putSchema(projectId, { name, decisions, confidence: true });
    setSchema(saved);
    return saved;
  }, { success: "Decision schema enregistré" });

  const addExample = useAction(async () => {
    if (!projectId) return;
    await api.decisionModels.add(projectId, "train", exampleInput, exampleDecision);
    setExampleInput("");
    setExampleDecision("");
    load();
  }, { success: "Exemple ajouté au dataset" });

  const runEvaluation = useAction(async () => {
    if (!projectId) return;
    const result = await api.decisionModels.evaluate(projectId);
    setEvaluation(result);
    return result;
  }, { success: "Évaluation terminée" });

  const runInfer = useAction(async () => {
    if (!projectId) return;
    const result = await api.decisionModels.infer(projectId, inferInput);
    setInferResult(result);
    return result;
  });

  if (!projectId) return <EmptyState>Sélectionnez un projet pour gérer ses Decision Models.</EmptyState>;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Decision Models"
        description="Modèles de décision structurée : entrée → décision parmi un ensemble fermé de valeurs, avec score de confiance optionnel."
      />

      <Card>
        <SectionTitle>Decision Schema</SectionTitle>
        {schema === undefined ? (
          <Skeleton className="h-20" />
        ) : (
          <div className="space-y-3 max-w-xl">
            <Field label="Nom">
              <Input value={name} onChange={setName} placeholder="Ticket Router" />
            </Field>
            <Field label="Décisions autorisées (séparées par des virgules)" hint="ex : billing, technical, sales, spam">
              <Input value={decisionsText} onChange={setDecisionsText} placeholder="billing, technical, sales, spam" />
            </Field>
            <Button variant="accent" onClick={() => saveSchema.run()} disabled={saveSchema.busy || !name || !decisionsText}>
              {saveSchema.busy ? "Enregistrement…" : "Enregistrer le schema"}
            </Button>
          </div>
        )}
      </Card>

      {schema && (
        <>
          <Card>
            <SectionTitle>Dataset</SectionTitle>
            {stats && (
              <div className="mb-4 text-sm text-text-secondary space-y-1">
                <p>Samples : {stats.total_examples} — Classes : {stats.classes.length}</p>
                {stats.classes.length > 0 && (
                  <p>
                    Plus petite classe : {stats.smallest_class} · Plus grande : {stats.largest_class} · Ratio d&apos;équilibre :{" "}
                    {stats.balance_ratio !== null ? stats.balance_ratio.toFixed(2) : "n/a"}
                  </p>
                )}
              </div>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-2xl">
              <Field label="Input">
                <Textarea value={exampleInput} onChange={setExampleInput} rows={2} placeholder="Mon paiement a été débité deux fois." />
              </Field>
              <Field label="Decision" hint={schema.decisions.join(" / ")}>
                <Input value={exampleDecision} onChange={setExampleDecision} placeholder="billing" />
              </Field>
            </div>
            <Button
              className="mt-3"
              onClick={() => addExample.run()}
              disabled={addExample.busy || !exampleInput || !exampleDecision}
            >
              {addExample.busy ? "Ajout…" : "Ajouter au train set"}
            </Button>
          </Card>

          <Card>
            <SectionTitle>Évaluation</SectionTitle>
            <Button variant="accent" onClick={() => runEvaluation.run()} disabled={runEvaluation.busy}>
              {runEvaluation.busy ? "Évaluation en cours…" : "Évaluer sur le test set"}
            </Button>
            {evaluation && (
              <div className="mt-4 space-y-4">
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
                  <Metric label="Accuracy" value={evaluation.accuracy} />
                  <Metric label="F1 (macro)" value={evaluation.macro_f1} />
                  <Metric label="Invalid output rate" value={evaluation.invalid_output_rate} danger />
                  <Metric label="Latence p95" value={evaluation.latency_ms_p95} suffix=" ms" raw />
                </div>
                <div>
                  <p className="text-xs text-text-muted mb-2">Matrice de confusion</p>
                  <ConfusionMatrix rows={evaluation.confusion_matrix} labels={schema.decisions} />
                </div>
              </div>
            )}
          </Card>

          <Card>
            <SectionTitle>Decision Gateway — test manuel</SectionTitle>
            <div className="flex gap-2 max-w-xl">
              <Input value={inferInput} onChange={setInferInput} placeholder="Entrée à classifier" className="flex-1" />
              <Button variant="accent" onClick={() => runInfer.run()} disabled={runInfer.busy || !inferInput}>
                {runInfer.busy ? "…" : "Décider"}
              </Button>
            </div>
            {inferResult && (
              <p className="mt-3 text-sm text-text-secondary">
                Décision : <span className="font-mono text-text-primary">{inferResult.decision}</span>
                {inferResult.confidence !== null && <> — confiance {(inferResult.confidence * 100).toFixed(0)}%</>}
              </p>
            )}
          </Card>
        </>
      )}
    </div>
  );
}

function Metric({ label, value, suffix = "", danger, raw }: { label: string; value: number; suffix?: string; danger?: boolean; raw?: boolean }) {
  const display = raw ? value.toFixed(0) : `${(value * 100).toFixed(1)}%`;
  return (
    <div className="border border-border rounded-md p-2.5">
      <p className="text-text-muted text-xs">{label}</p>
      <p className={`font-mono text-base mt-0.5 ${danger && value > 0.05 ? "text-error" : "text-text-primary"}`}>
        {display}
        {suffix}
      </p>
    </div>
  );
}
