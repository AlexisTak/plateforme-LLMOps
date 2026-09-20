const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(readonly status: number, readonly path: string, readonly detail: string) {
    super(`${status} ${path}: ${detail}`);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options?.headers || {}) },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    let detail = text;
    try {
      const parsed = JSON.parse(text);
      if (parsed && typeof parsed.detail === "string") detail = parsed.detail;
    } catch {
      // not JSON, use raw text
    }
    throw new ApiError(res.status, path, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

const p = (project: string) => `/api/projects/${encodeURIComponent(project)}`;

export type Message = { role: "system" | "user" | "assistant"; content: string };

export type ConversationSummary = { id: string; title: string; created_at: string; updated_at: string; message_count: number };
export type ConversationMessage = { id: string; role: "user" | "assistant"; content: string; rag_chunks: string[]; created_at: string };
export type ConversationDetail = ConversationSummary & { messages: ConversationMessage[] };

export type DatasetCategorySummary = { category: string; files: string[]; example_count: number };
export type DatasetExample = { id: string; file: string; index: number; messages: Message[] };
export type ValidationFinding = { file: string; line: number; level: string; message: string };
export type NearDuplicatePair = { file_a: string; line_a: number; file_b: string; line_b: number; similarity: number };
export type SplitLeak = { train_ref: string; split_file: string; split_ref: string };
export type ValidationResult = {
  total_examples: number;
  total_files: number;
  errors: number;
  warnings: number;
  findings: ValidationFinding[];
  near_duplicates: NearDuplicatePair[];
  near_duplicate_scan_skipped: boolean;
  split_leaks: SplitLeak[];
};
export type DatasetStats = {
  total_examples: number;
  by_category: Record<string, number>;
  char_length_mean: number;
  char_length_p95: number;
  char_length_max: number;
  exact_duplicates: number;
};
export type DuplicateExample = { file: string; line: number };
export type DeduplicateResult = {
  dry_run: boolean;
  total_before: number;
  total_after: number;
  removed: number;
  removed_by_file: Record<string, number>;
  duplicates: DuplicateExample[];
};
export type CurrentDatasetVersion = { version: string | null; train: number; validation: number; test: number };
export type DatasetVersionManifest = { version: string; dataset: string; author: string; created_at: string; splits: Record<string, number>; example_count: number; sha256: string; seed: number };
export type DatasetVersionDiffEntry = { split: string; id: string; summary: string };
export type DatasetVersionDiff = { from_version: string; to_version: string; added: DatasetVersionDiffEntry[]; removed: DatasetVersionDiffEntry[]; modified: DatasetVersionDiffEntry[] };

export type DecisionSchema = { name: string; decisions: string[]; confidence: boolean };
export type DecisionExample = { id: string; file: string; index: number; input: string; decision: string };
export type DecisionValidationFinding = { file: string; line: number; level: string; message: string };
export type DecisionValidationResult = { total_examples: number; errors: number; warnings: number; findings: DecisionValidationFinding[] };
export type DecisionClassStat = { decision: string; count: number };
export type DecisionDatasetStats = {
  total_examples: number;
  by_split: Record<string, number>;
  classes: DecisionClassStat[];
  smallest_class: number;
  largest_class: number;
  balance_ratio: number | null;
};
export type DecisionClassMetric = { decision: string; precision: number; recall: number; f1: number; support: number };
export type DecisionConfusionRow = { actual: string; predicted: Record<string, number> };
export type DecisionEvaluationResult = {
  n: number;
  accuracy: number;
  macro_precision: number;
  macro_recall: number;
  macro_f1: number;
  invalid_output_rate: number;
  per_class: DecisionClassMetric[];
  confusion_matrix: DecisionConfusionRow[];
  latency_ms_p50: number;
  latency_ms_p95: number;
  generated_at: string;
};
export type DecisionResult = { decision: string; confidence: number | null; model: string; latency_ms: number; fallback_used: boolean };
export type DecisionFallbackConfig = { enabled: boolean; fallback_project_id: string | null; threshold: number };

export type EvalSummaryMetric = {
  n: number;
  plain_text_passed?: number;
  plain_text_total?: number;
  plain_text_pct?: number | null;
  json_valid_passed?: number;
  json_valid_total?: number;
  json_valid_pct: number | null;
  has_expected_keys_passed?: number;
  has_expected_keys_total?: number;
  has_expected_keys_pct: number | null;
  concise_passed?: number;
  concise_total?: number;
  concise_pct: number | null;
};

export type BenchmarkCase = {
  id: string;
  category: string;
  user: string;
  checks: {
    expect_json: boolean;
    expect_keys: string[];
    max_chars: number;
    expect_plain_text: boolean;
  };
  review: string[];
};

export type EvaluationReport = {
  content: string;
  path: string;
  metadata: { generated_at?: string; dataset_version?: string | null };
  stale_reasons: string[];
  comparison?: { comparable: boolean; previous_generated_at?: string; deltas: Record<string, Record<string, number>> } | null;
  outputs?: Record<string, EvaluationOutput[]>;
};

export type EvaluationOutput = {
  id: string;
  category: string;
  prompt?: string;
  response: string;
  plain_text?: boolean | null;
  concise: boolean;
};

export type ExperimentResult = {
  experiment_id: string;
  config_path: string;
  notes?: string;
  dataset_version?: string;
  base_model?: string;
  lora?: { r: number; alpha: number; dropout: number };
  train_loss?: number;
  eval_loss?: number;
  train_duration_minutes?: number;
  peak_vram_mb?: number;
  adapter_size_mb?: number;
  output_dir?: string;
};

export type TrainingConfigSummary = {
  filename: string;
  experiment_id: string;
  notes?: string;
  base_model: string;
  lora_r: number;
  dataset_version: string;
  output_dir: string;
  has_result: boolean;
};

export type Project = {
  id: string;
  base_model: string;
  label: string;
  project_type: "general" | "agent" | "developer" | "business";
  model_kind: "generation" | "decision";
  purpose: string;
  output_mode: "natural" | "json" | "flexible";
  ollama_equivalent?: string | null;
  inference_model?: string | null;
  added_at: string;
  dataset_examples: number;
  rag_documents: number;
  experiment_count: number;
};

export type InferenceConfig = {
  model: string;
};
export type ProjectSettings = {
  id: string; label: string; project_type: Project["project_type"]; purpose: string;
  output_mode: Project["output_mode"]; base_model: string; inference_model: string;
  system_prompt: string; max_assistant_chars: number;
};

export type CreateProjectParams = {
  id: string;
  label?: string;
  base_model: string;
  project_type: Project["project_type"];
  model_kind?: Project["model_kind"];
  purpose: string;
  output_mode: Project["output_mode"];
  system_prompt?: string;
  ollama_equivalent?: string | null;
};

export type RagCategory = "methods" | "research" | "product" | "other";
export type RoleName = "viewer" | "operator" | "reviewer" | "admin";
export type RagCategoryAcl = { category: RagCategory; minimum_role: RoleName };
export const RAG_CATEGORIES: RagCategory[] = ["methods", "research", "product", "other"];
export type RagSearchResult = { chunk_id: string; doc_id: string; category: string; text: string; score: number };
export type RagEvalQuery = { id: string; query: string; relevant_doc_ids: string[] };
export type RagEvalQueryChunk = { chunk_id: string; doc_id: string; category: string; score: number; text: string };
export type RagEvalQueryResult = { id: string; query: string; relevant_doc_ids: string[]; hit: boolean; rank: number | null; chunks: RagEvalQueryChunk[] };
export type RagEvalResult = { top_k: number; n_queries: number; recall_at_k: number | null; mrr: number | null; queries: RagEvalQueryResult[] };
export type RagDocument = {
  filename: string;
  category: string;
  size_bytes: number;
  char_count: number;
  preview: string;
  reindex_job_id?: string | null;
};

export type TrainingMetricPoint = { step: number; epoch?: number | null; loss?: number | null; eval_loss?: number | null; learning_rate?: number | null };

export type ModelPreflight = {
  model: string;
  ready: boolean;
  accessible: boolean;
  architecture?: string | null;
  parameter_count?: number | null;
  estimated_download_gb?: number | null;
  estimated_vram_gb?: number | null;
  available_vram_gb?: number | null;
  cuda_available: boolean;
  warnings: string[];
  errors: string[];
  technical_detail?: string | null;
};

export type CreateConfigParams = {
  name: string;
  notes?: string;
  dataset_version: string;
  lora_r?: number;
  lora_alpha?: number;
  lora_dropout?: number;
  epochs?: number;
  learning_rate?: number;
  batch_size?: number;
  gradient_accumulation_steps?: number;
  warmup_steps?: number;
};

export type JobStatus = {
  job_id: string;
  kind: "training" | "evaluation" | "reindex" | "pipeline" | "sweep";
  status: "running" | "completed" | "failed" | "stopped";
  config_filename?: string | null;
  started_at: string;
  finished_at?: string | null;
  return_code?: number | null;
  log_tail: string[];
  result?: Record<string, unknown> | null;
  error_code?: string | null;
  error_message?: string | null;
  suggestion?: string | null;
};

export type PackageCheck = { package: string; installed: string | null; expected: string | null; ok: boolean };
export type SystemHealth = {
  ok: boolean;
  torch_cuda: { torch_version: string | null; is_cpu_only_build: boolean | null; cuda_available: boolean; device_name: string | null; ok: boolean };
  packages: PackageCheck[];
  gpu: { name: string; memory_total_mb: number; memory_used_mb: number; utilization_pct: number } | null;
  disk: { free_gb: number; total_gb: number };
  ollama: { running: boolean; models: string[] };
};

export type EnterpriseContext = {
  actor: { id: string; email: string; role: "viewer" | "operator" | "reviewer" | "admin"; name: string };
  auth_mode: "local" | "proxy";
  audit_chain_valid: boolean;
};
export type EnterpriseMetrics = {
  requests_total?: number; status_2xx?: number; status_4xx?: number; status_5xx?: number;
  uptime_seconds: number; latency_avg_ms: number; latency_p95_ms: number;
  jobs_running: number; jobs_failed: number; jobs_total: number;
};
export type ModelVersion = {
  id: string; project_id: string; version: string; status: "draft" | "evaluated" | "approved" | "production" | "archived";
  model: string; dataset_version?: string | null; benchmark_generated_at?: string | null;
  created_at: string; created_by: string; approved_at?: string | null; approved_by?: string | null; notes: string;
};
export type AuditEvent = {
  id: string; created_at: string; actor_id: string; action: string; resource_type: string;
  resource_id?: string | null; project_id?: string | null; details: Record<string, unknown>; event_hash: string;
};
export type ProjectQuota = {
  project_id: string; max_concurrent_jobs: number; max_daily_jobs: number; max_storage_gb: number; running_jobs?: number; storage_used_gb?: number;
};
export type AgentBudget = {
  project_id: string; max_tokens_per_day: number; max_duration_ms_per_day: number; max_tool_calls_per_day: number;
  tokens_used?: number; duration_ms_used?: number; tool_calls_used?: number;
};
export type ProjectMember = {
  project_id: string; actor_id: string; email: string; name: string;
  role: "viewer" | "operator" | "reviewer" | "admin"; created_at: string;
};
export type Execution = {
  id: string; project_id: string; actor_id: string; status: "running" | "completed" | "failed";
  model: string; adapter?: string | null; rag_requested: number; rag_used: number;
  prompt_chars: number; response_chars?: number | null; estimated_tokens?: number | null;
  duration_ms?: number | null; started_at: string; finished_at?: string | null; error_code?: string | null;
};
export type TraceEvent = { execution_id: string; seq: number; type: string; payload: Record<string, unknown>; created_at: string };
export type ExecutionDetail = Execution & { events: TraceEvent[] };
export type Provider = {
  id: string; project_id: string; name: string; type: "ollama" | "openai-compatible" | "anthropic-compatible";
  base_url: string; model: string; api_key_env?: string | null; enabled: number; created_at: string;
};
export type ToolRiskLevel = "low" | "medium" | "high" | "critical";
export type ToolDefinition = { id: string; project_id: string; name: string; method: "GET" | "POST" | "MCP"; url: string; approval_required: number; timeout_seconds: number; max_response_bytes: number; enabled: number; created_at: string; risk_level: ToolRiskLevel; connector_type?: "http" | "mcp"; connector_id?: string | null; action?: string | null; description?: string | null; input_schema?: Record<string, unknown> | null };
export type Approval = { id: string; project_id: string; tool_id: string; tool_name: string; requester_id: string; status: "pending" | "processing" | "approved" | "denied" | "failed"; arguments: Record<string, unknown>; result?: Record<string, unknown> | null; created_at: string; decided_at?: string | null; decided_by?: string | null };
export type ToolPolicy = { id: string; project_id: string; name: string; effect: "allow" | "deny" | "require_approval"; tool_id?: string | null; tool_name?: string | null; priority: number; enabled: number; created_at: string };
export type McpServer = { id: string; project_id: string; name: string; url: string; api_key_env?: string | null; enabled: number; created_at: string };

export type OpportunityStatus = "idee" | "analyse" | "validation" | "poc" | "pilote" | "commercialisation" | "production" | "abandonnee";
export type OpportunityScores = {
  market: number; profitability: number; feasibility: number; commercialization: number;
  scalability: number; retention: number; risk: number;
};
export type OpportunityScore = {
  total: number;
  label: "priorite_strategique" | "tres_interessant" | "a_tester" | "risque" | "a_eviter";
  breakdown: OpportunityScores;
};
export const SCORE_LABELS: Record<OpportunityScore["label"], { emoji: string; text: string }> = {
  priorite_strategique: { emoji: "⭐", text: "Priorité stratégique" },
  tres_interessant: { emoji: "🟢", text: "Très intéressant" },
  a_tester: { emoji: "🟠", text: "À tester" },
  risque: { emoji: "🟡", text: "Risqué" },
  a_eviter: { emoji: "🔴", text: "À éviter" },
};
export type OpportunityFields = {
  name: string; description: string; customer_problem: string; proposed_solution: string;
  target_customer: string; sector: string; value_proposition: string; technologies: string[];
  maturity: string; dev_difficulty: number; sales_difficulty: number; competition: string;
  differentiation: string; business_model: string; setup_cost: number; monthly_cost: number;
  setup_price: number; monthly_price: number; estimated_margin_pct: number;
  recurring_revenue_potential: number; risks: string[]; regulatory_constraints: string;
};
export type Opportunity = OpportunityFields & {
  id: string; status: OpportunityStatus; created_at: string; updated_at: string; created_by: string;
  scores: OpportunityScores; score: OpportunityScore;
};
export type OpportunityKpi = {
  id: string; opportunity_id: string; category: "commercial" | "financier" | "ia" | "retention";
  name: string; unit: string; current_value: number | null; target_value: number | null;
  previous_value: number | null; measured_at: string | null; higher_is_better: number;
  created_at: string; evolution_pct: number | null; trend: "hausse" | "baisse" | "stable";
  status: "atteint" | "attention" | "non_atteint" | "inconnu";
};
export type OpportunityAnalysis = {
  id: string; opportunity_id: string; project_id: string; provider_id: string;
  result: Record<string, unknown>; recommended_score: number | null; created_at: string; created_by: string;
};

export const api = {
  health: () => request<{ status: string }>("/api/health"),
  systemHealth: () => request<SystemHealth>("/api/system/health"),

  projects: {
    list: () => request<Project[]>("/api/projects"),
    create: (params: CreateProjectParams) =>
      request<Project>("/api/projects", { method: "POST", body: JSON.stringify(params) }),
    remove: (id: string) => request<{ deleted: boolean }>(`/api/projects/${encodeURIComponent(id)}`, { method: "DELETE" }),
    inference: (id: string) => request<InferenceConfig>(`/api/projects/${encodeURIComponent(id)}/inference`),
    updateInference: (id: string, model: string) =>
      request<InferenceConfig>(`/api/projects/${encodeURIComponent(id)}/inference`, {
        method: "PATCH",
        body: JSON.stringify({ model }),
      }),
    settings: (id: string) => request<ProjectSettings>(`/api/projects/${encodeURIComponent(id)}/settings`),
    updateSettings: (id: string, settings: Omit<ProjectSettings, "id" | "base_model">) =>
      request<ProjectSettings>(`/api/projects/${encodeURIComponent(id)}/settings`, { method: "PUT", body: JSON.stringify(settings) }),
  },

  dataset: {
    categories: (project: string) => request<DatasetCategorySummary[]>(`${p(project)}/dataset/categories`),
    list: (project: string, category: string) => request<DatasetExample[]>(`${p(project)}/dataset/${category}`),
    add: (project: string, category: string, file: string, messages: Message[]) =>
      request<DatasetExample>(`${p(project)}/dataset/${category}`, { method: "POST", body: JSON.stringify({ file, messages }) }),
    update: (project: string, category: string, id: string, messages: Message[]) =>
      request<DatasetExample>(`${p(project)}/dataset/${category}/${id}`, { method: "PUT", body: JSON.stringify({ messages }) }),
    remove: (project: string, category: string, id: string) =>
      request<{ deleted: boolean }>(`${p(project)}/dataset/${category}/${id}`, { method: "DELETE" }),
    validate: (project: string) => request<ValidationResult>(`${p(project)}/dataset/validate`, { method: "POST" }),
    prepare: (project: string, version: string, seed = 42) =>
      request<{ version: string; train: number; validation: number; test: number }>(`${p(project)}/dataset/prepare`, {
        method: "POST",
        body: JSON.stringify({ version, seed }),
      }),
    stats: (project: string) => request<DatasetStats>(`${p(project)}/dataset/meta/stats`),
    deduplicate: (project: string, dryRun = true) =>
      request<DeduplicateResult>(`${p(project)}/dataset/deduplicate?dry_run=${dryRun}`, { method: "POST" }),
    currentVersion: (project: string) => request<CurrentDatasetVersion>(`${p(project)}/dataset/meta/version`),
    versions: (project: string) => request<DatasetVersionManifest[]>(`${p(project)}/dataset/versions`),
    versionDiff: (project: string, from: string, to: string) =>
      request<DatasetVersionDiff>(`${p(project)}/dataset/versions/${encodeURIComponent(from)}/diff/${encodeURIComponent(to)}`),
  },

  decisionModels: {
    getSchema: (project: string) => request<DecisionSchema | null>(`${p(project)}/decision/schema`),
    putSchema: (project: string, schema: DecisionSchema) =>
      request<DecisionSchema>(`${p(project)}/decision/schema`, { method: "PUT", body: JSON.stringify(schema) }),
    list: (project: string, split: "train" | "validation" | "test") =>
      request<DecisionExample[]>(`${p(project)}/decision/dataset/${split}`),
    add: (project: string, split: "train" | "validation" | "test", input: string, decision: string) =>
      request<DecisionExample>(`${p(project)}/decision/dataset`, {
        method: "POST",
        body: JSON.stringify({ file: `${split}.jsonl`, input, decision }),
      }),
    remove: (project: string, split: string, index: number) =>
      request<{ deleted: boolean }>(`${p(project)}/decision/dataset/${split}/${index}`, { method: "DELETE" }),
    validate: (project: string) => request<DecisionValidationResult>(`${p(project)}/decision/dataset/validate`),
    stats: (project: string) => request<DecisionDatasetStats>(`${p(project)}/decision/dataset/stats`),
    evaluate: (project: string) => request<DecisionEvaluationResult>(`${p(project)}/decision/evaluate`, { method: "POST" }),
    infer: (project: string, input: string) =>
      request<DecisionResult>(`${p(project)}/decision/infer`, { method: "POST", body: JSON.stringify({ input }) }),
    getFallback: (project: string) => request<DecisionFallbackConfig>(`${p(project)}/decision/fallback`),
    putFallback: (project: string, config: DecisionFallbackConfig) =>
      request<DecisionFallbackConfig>(`${p(project)}/decision/fallback`, { method: "PUT", body: JSON.stringify(config) }),
  },

  experiments: {
    list: (project: string) => request<ExperimentResult[]>(`${p(project)}/experiments`),
    compare: (project: string, ids: string[]) =>
      request<ExperimentResult[]>(`${p(project)}/experiments/compare?ids=${encodeURIComponent(ids.join(","))}`),
    report: (project: string) => request<EvaluationReport>(`${p(project)}/evaluation/report`),
    reportSummary: (project: string) => request<Record<string, EvalSummaryMetric>>(`${p(project)}/evaluation/report/summary`),
  },

  training: {
    preflight: (project: string, model: string) =>
      request<ModelPreflight>(`${p(project)}/training/preflight?model=${encodeURIComponent(model)}`),
    configs: (project: string) => request<TrainingConfigSummary[]>(`${p(project)}/training/configs`),
    start: (project: string, config_filename: string, resume = false) =>
      request<JobStatus>(`${p(project)}/training/start`, { method: "POST", body: JSON.stringify({ config_filename, resume }) }),
    pipeline: (project: string, config_filename: string, dataset_version: string, resume = false) =>
      request<JobStatus>(`${p(project)}/training/pipeline`, {
        method: "POST",
        body: JSON.stringify({ config_filename, dataset_version, resume }),
      }),
    createConfig: (project: string, params: CreateConfigParams) =>
      request<TrainingConfigSummary>(`${p(project)}/training/configs`, { method: "POST", body: JSON.stringify(params) }),
    sweep: (project: string, dataset_version: string, resume = false) =>
      request<JobStatus>(`${p(project)}/training/sweep`, { method: "POST", body: JSON.stringify({ dataset_version, resume }) }),
  },

  evaluation: {
    benchmark: (project: string) => request<BenchmarkCase[]>(`${p(project)}/evaluation/benchmark`),
    createCase: (project: string, item: BenchmarkCase) => request<BenchmarkCase>(`${p(project)}/evaluation/benchmark`, { method: "POST", body: JSON.stringify(item) }),
    updateCase: (project: string, caseId: string, item: BenchmarkCase) => request<BenchmarkCase>(`${p(project)}/evaluation/benchmark/${encodeURIComponent(caseId)}`, { method: "PUT", body: JSON.stringify(item) }),
    removeCase: (project: string, caseId: string) => request<{ deleted: boolean }>(`${p(project)}/evaluation/benchmark/${encodeURIComponent(caseId)}`, { method: "DELETE" }),
    run: (project: string) => request<JobStatus>(`${p(project)}/evaluation/run`, { method: "POST" }),
  },

  jobs: {
    list: (project?: string) => request<JobStatus[]>(project ? `${p(project)}/jobs` : "/api/jobs"),
    get: (id: string) => request<JobStatus>(`/api/jobs/${id}`),
    stop: (id: string) => request<{ stopped: boolean }>(`/api/jobs/${id}/stop`, { method: "POST" }),
    metrics: (id: string) => request<TrainingMetricPoint[]>(`/api/jobs/${id}/metrics`),
  },

  chat: {
    adapters: (project: string) => request<{ adapters: string[] }>(`${p(project)}/chat/adapters`),
    send: (project: string, message: string, adapter: string | null, rag: boolean, system_prompt?: string,
           history: { role: "user" | "assistant"; content: string }[] = [], user_context: Record<string, string> = {},
           conversation_id: string | null = null) =>
      request<{ response: string; adapter: string | null; rag_used: boolean; rag_chunks: string[]; conversation_id: string | null }>(`${p(project)}/chat`, {
        method: "POST",
        body: JSON.stringify({ message, adapter, rag, system_prompt, history, user_context, conversation_id, persist: conversation_id !== null }),
      }),
    stream: async (project: string, message: string, adapter: string | null, rag: boolean,
                   history: { role: "user" | "assistant"; content: string }[] = [],
                   user_context: Record<string, string> = {},
                   onEvent: (event: string, payload: Record<string, unknown>) => void,
                   conversation_id: string | null = null, persist = false) => {
      const res = await fetch(`${API_URL}${p(project)}/chat/stream`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, adapter, rag, history, user_context, conversation_id, persist: persist || conversation_id !== null }),
      });
      if (!res.ok) throw new Error(`${res.status} chat stream: ${await res.text().catch(() => res.statusText)}`);
      if (!res.body) throw new Error("Le navigateur ne fournit pas le flux de réponse");
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value, { stream: !done }).replaceAll("\r\n", "\n");
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";
        for (const frame of frames) {
          const event = frame.split("\n").find((line) => line.startsWith("event:"))?.slice(6).trim() || "message";
          const data = frame.split("\n").filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trim()).join("\n");
          if (!data) continue;
          const payload = JSON.parse(data) as Record<string, unknown>;
          onEvent(event, payload);
          if (event === "error") throw new Error(String(payload.detail || "La génération a échoué"));
        }
        if (done) break;
      }
    },
    conversations: (project: string) => request<ConversationSummary[]>(`${p(project)}/chat/conversations`),
    createConversation: (project: string, title = "Nouvelle conversation") =>
      request<ConversationSummary>(`${p(project)}/chat/conversations`, { method: "POST", body: JSON.stringify({ title }) }),
    getConversation: (project: string, conversationId: string) =>
      request<ConversationDetail>(`${p(project)}/chat/conversations/${encodeURIComponent(conversationId)}`),
    renameConversation: (project: string, conversationId: string, title: string) =>
      request<ConversationSummary>(`${p(project)}/chat/conversations/${encodeURIComponent(conversationId)}`, {
        method: "PATCH", body: JSON.stringify({ title }),
      }),
    deleteConversation: (project: string, conversationId: string) =>
      request<void>(`${p(project)}/chat/conversations/${encodeURIComponent(conversationId)}`, { method: "DELETE" }),
  },

  rag: {
    search: (project: string, query: string, top_k = 3) =>
      request<RagSearchResult[]>(`${p(project)}/rag/search`, {
        method: "POST",
        body: JSON.stringify({ query, top_k }),
      }),
    documents: (project: string) => request<RagDocument[]>(`${p(project)}/rag/documents`),
    createDocument: (project: string, filename: string, category: RagCategory, content: string) =>
      request<RagDocument>(`${p(project)}/rag/documents`, { method: "POST", body: JSON.stringify({ filename, category, content }) }),
    uploadDocument: async (project: string, file: File, category: RagCategory): Promise<RagDocument> => {
      const form = new FormData();
      form.append("file", file);
      form.append("category", category);
      const res = await fetch(`${API_URL}${p(project)}/rag/documents/upload`, { method: "POST", body: form });
      if (!res.ok) throw new Error(`${res.status} upload: ${await res.text().catch(() => res.statusText)}`);
      return res.json();
    },
    deleteDocument: (project: string, category: string, filename: string) =>
      request<{ deleted: boolean; reindex_job_id: string | null }>(
        `${p(project)}/rag/documents/${encodeURIComponent(category)}/${encodeURIComponent(filename)}`,
        { method: "DELETE" }
      ),
    reindex: (project: string) => request<JobStatus>(`${p(project)}/rag/reindex`, { method: "POST" }),
    evalQueries: (project: string) => request<RagEvalQuery[]>(`${p(project)}/rag/eval-queries`),
    createEvalQuery: (project: string, query: RagEvalQuery) =>
      request<RagEvalQuery>(`${p(project)}/rag/eval-queries`, { method: "POST", body: JSON.stringify(query) }),
    deleteEvalQuery: (project: string, id: string) =>
      request<{ deleted: boolean }>(`${p(project)}/rag/eval-queries/${encodeURIComponent(id)}`, { method: "DELETE" }),
    evaluate: (project: string, topK = 5) =>
      request<RagEvalResult>(`${p(project)}/rag/evaluate?top_k=${topK}`, { method: "POST" }),
    acls: (project: string) => request<RagCategoryAcl[]>(`${p(project)}/rag/acls`),
    updateAcl: (project: string, category: RagCategory, minimum_role: RoleName) =>
      request<RagCategoryAcl>(`${p(project)}/rag/acls`, { method: "PUT", body: JSON.stringify({ category, minimum_role }) }),
  },

  enterprise: {
    context: () => request<EnterpriseContext>("/api/enterprise/context"),
    metrics: () => request<EnterpriseMetrics>("/api/enterprise/metrics"),
    audit: (project?: string) => request<AuditEvent[]>(`/api/enterprise/audit${project ? `?project_id=${encodeURIComponent(project)}` : ""}`),
    registry: (project: string) => request<ModelVersion[]>(`/api/enterprise/projects/${encodeURIComponent(project)}/registry`),
    createVersion: (project: string, version: string, notes: string) => request<ModelVersion>(`/api/enterprise/projects/${encodeURIComponent(project)}/registry`, { method: "POST", body: JSON.stringify({ version, notes }) }),
    transition: (project: string, id: string, status: ModelVersion["status"]) => request<ModelVersion>(`/api/enterprise/projects/${encodeURIComponent(project)}/registry/${encodeURIComponent(id)}/transition`, { method: "POST", body: JSON.stringify({ status }) }),
    quota: (project: string) => request<ProjectQuota>(`/api/enterprise/projects/${encodeURIComponent(project)}/quota`),
    updateQuota: (project: string, quota: Omit<ProjectQuota, "project_id" | "running_jobs">) => request<ProjectQuota>(`/api/enterprise/projects/${encodeURIComponent(project)}/quota`, { method: "PUT", body: JSON.stringify(quota) }),
    budget: (project: string) => request<AgentBudget>(`/api/enterprise/projects/${encodeURIComponent(project)}/budget`),
    updateBudget: (project: string, budget: Pick<AgentBudget, "max_tokens_per_day" | "max_duration_ms_per_day" | "max_tool_calls_per_day">) =>
      request<AgentBudget>(`/api/enterprise/projects/${encodeURIComponent(project)}/budget`, { method: "PUT", body: JSON.stringify(budget) }),
    deployment: (project: string) => request<Record<string, unknown>>(`/api/enterprise/projects/${encodeURIComponent(project)}/deployment`),
    members: (project: string) => request<ProjectMember[]>(`/api/enterprise/projects/${encodeURIComponent(project)}/members`),
    updateMember: (project: string, member: Pick<ProjectMember, "actor_id" | "email" | "name" | "role">) => request<ProjectMember>(`/api/enterprise/projects/${encodeURIComponent(project)}/members`, { method: "PUT", body: JSON.stringify(member) }),
    removeMember: (project: string, actorId: string) => request<{ deleted: boolean }>(`/api/enterprise/projects/${encodeURIComponent(project)}/members/${encodeURIComponent(actorId)}`, { method: "DELETE" }),
    backupUrl: (project: string) => `${API_URL}/api/enterprise/projects/${encodeURIComponent(project)}/backup`,
    executions: (project: string) => request<Execution[]>(`/api/enterprise/projects/${encodeURIComponent(project)}/executions`),
    execution: (project: string, id: string) => request<ExecutionDetail>(`/api/enterprise/projects/${encodeURIComponent(project)}/executions/${encodeURIComponent(id)}`),
    executionExportUrl: (project: string, id: string) => `${API_URL}/api/enterprise/projects/${encodeURIComponent(project)}/executions/${encodeURIComponent(id)}/export`,
    sbomUrl: (project: string, id: string) => `${API_URL}/api/enterprise/projects/${encodeURIComponent(project)}/registry/${encodeURIComponent(id)}/sbom`,
    providers: (project: string) => request<Provider[]>(`/api/enterprise/projects/${encodeURIComponent(project)}/providers`),
    updateProvider: (project: string, provider: Omit<Provider, "id" | "project_id" | "created_at" | "enabled"> & { enabled: boolean }) => request<Provider>(`/api/enterprise/projects/${encodeURIComponent(project)}/providers`, { method: "PUT", body: JSON.stringify(provider) }),
    removeProvider: (project: string, id: string) => request<{ deleted: boolean }>(`/api/enterprise/projects/${encodeURIComponent(project)}/providers/${encodeURIComponent(id)}`, { method: "DELETE" }),
    testProvider: (project: string, id: string) => request<{ ok: boolean; latency_ms: number; model: string }>(`/api/enterprise/projects/${encodeURIComponent(project)}/providers/${encodeURIComponent(id)}/test`, { method: "POST" }),
    tools: (project: string) => request<ToolDefinition[]>(`/api/enterprise/projects/${encodeURIComponent(project)}/tools`),
    updateTool: (project: string, tool: { name: string; method: "GET" | "POST"; url: string; approval_required: boolean; timeout_seconds: number; max_response_bytes: number; risk_level: ToolRiskLevel }) => request<ToolDefinition>(`/api/enterprise/projects/${encodeURIComponent(project)}/tools`, { method: "PUT", body: JSON.stringify(tool) }),
    executeTool: (project: string, id: string, args: Record<string, unknown>) => request<Record<string, unknown>>(`/api/enterprise/projects/${encodeURIComponent(project)}/tools/${encodeURIComponent(id)}/execute`, { method: "POST", body: JSON.stringify({ arguments: args }) }),
    approvals: (project: string) => request<Approval[]>(`/api/enterprise/projects/${encodeURIComponent(project)}/approvals`),
    decideApproval: (project: string, id: string, decision: "approved" | "denied") => request<Approval>(`/api/enterprise/projects/${encodeURIComponent(project)}/approvals/${encodeURIComponent(id)}/decision`, { method: "POST", body: JSON.stringify({ decision }) }),
    toolPolicies: (project: string) => request<ToolPolicy[]>(`/api/enterprise/projects/${encodeURIComponent(project)}/tool-policies`),
    updateToolPolicy: (project: string, policy: Pick<ToolPolicy, "name" | "effect" | "tool_id" | "priority"> & { enabled: boolean }) => request<ToolPolicy>(`/api/enterprise/projects/${encodeURIComponent(project)}/tool-policies`, { method: "PUT", body: JSON.stringify(policy) }),
    removeToolPolicy: (project: string, id: string) => request<{ deleted: boolean }>(`/api/enterprise/projects/${encodeURIComponent(project)}/tool-policies/${encodeURIComponent(id)}`, { method: "DELETE" }),
    mcpServers: (project: string) => request<McpServer[]>(`/api/enterprise/projects/${encodeURIComponent(project)}/mcp-servers`),
    updateMcpServer: (project: string, server: Pick<McpServer, "name" | "url" | "api_key_env"> & { enabled: boolean }) => request<McpServer>(`/api/enterprise/projects/${encodeURIComponent(project)}/mcp-servers`, { method: "PUT", body: JSON.stringify(server) }),
    syncMcpServer: (project: string, id: string) => request<{ discovered: number; imported: number; skipped: number; tools: ToolDefinition[] }>(`/api/enterprise/projects/${encodeURIComponent(project)}/mcp-servers/${encodeURIComponent(id)}/sync`, { method: "POST" }),
  },

  opportunities: {
    list: () => request<Opportunity[]>("/api/opportunities"),
    dashboard: () => request<Opportunity[]>("/api/opportunities/dashboard"),
    create: (input: Partial<OpportunityFields> & Pick<OpportunityFields, "name">) =>
      request<Opportunity>("/api/opportunities", { method: "POST", body: JSON.stringify(input) }),
    get: (id: string) => request<Opportunity>(`/api/opportunities/${encodeURIComponent(id)}`),
    update: (id: string, input: OpportunityFields) =>
      request<Opportunity>(`/api/opportunities/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(input) }),
    updateStatus: (id: string, status: OpportunityStatus) =>
      request<Opportunity>(`/api/opportunities/${encodeURIComponent(id)}/status`, { method: "PUT", body: JSON.stringify({ status }) }),
    updateScores: (id: string, scores: OpportunityScores) =>
      request<Opportunity>(`/api/opportunities/${encodeURIComponent(id)}/scores`, { method: "PUT", body: JSON.stringify(scores) }),
    remove: (id: string) => request<{ deleted: boolean }>(`/api/opportunities/${encodeURIComponent(id)}`, { method: "DELETE" }),
    kpis: (id: string) => request<OpportunityKpi[]>(`/api/opportunities/${encodeURIComponent(id)}/kpis`),
    upsertKpi: (id: string, kpi: { name: string; category: OpportunityKpi["category"]; unit: string; current_value: number | null; target_value: number | null; higher_is_better: boolean }) =>
      request<OpportunityKpi>(`/api/opportunities/${encodeURIComponent(id)}/kpis`, { method: "PUT", body: JSON.stringify(kpi) }),
    analyze: (id: string, project_id: string, provider_id: string) =>
      request<OpportunityAnalysis>(`/api/opportunities/${encodeURIComponent(id)}/analyze`, { method: "POST", body: JSON.stringify({ project_id, provider_id }) }),
    analyses: (id: string) => request<OpportunityAnalysis[]>(`/api/opportunities/${encodeURIComponent(id)}/analyses`),
  },
};
