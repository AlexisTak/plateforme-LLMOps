const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options?.headers || {}) },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${path}: ${text}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

const p = (project: string) => `/api/projects/${encodeURIComponent(project)}`;

export type Message = { role: "system" | "user" | "assistant"; content: string };

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

export type EvalSummaryMetric = {
  n: number;
  plain_text_pct?: number | null;
  json_valid_pct: number | null;
  has_expected_keys_pct: number | null;
  concise_pct: number | null;
  safety_pass_pct: number | null;
};

export type EvaluationReport = {
  content: string;
  path: string;
  metadata: { generated_at?: string; dataset_version?: string | null };
  stale_reasons: string[];
  comparison?: { comparable: boolean; previous_generated_at?: string; deltas: Record<string, Record<string, number>> } | null;
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
  ollama_equivalent?: string | null;
  added_at: string;
  dataset_examples: number;
  rag_documents: number;
  experiment_count: number;
};

export type RagCategory = "methods" | "research" | "product" | "other";
export const RAG_CATEGORIES: RagCategory[] = ["methods", "research", "product", "other"];
export type RagSearchResult = { chunk_id: string; doc_id: string; category: string; text: string; score: number };
export type RagDocument = {
  filename: string;
  category: string;
  size_bytes: number;
  char_count: number;
  preview: string;
  reindex_job_id?: string | null;
};

export type TrainingMetricPoint = { step: number; epoch?: number | null; loss?: number | null; eval_loss?: number | null; learning_rate?: number | null };

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

export const api = {
  health: () => request<{ status: string }>("/api/health"),
  systemHealth: () => request<SystemHealth>("/api/system/health"),

  projects: {
    list: () => request<Project[]>("/api/projects"),
    create: (id: string, base_model: string, label?: string, ollama_equivalent?: string) =>
      request<Project>("/api/projects", { method: "POST", body: JSON.stringify({ id, base_model, label, ollama_equivalent }) }),
    remove: (id: string) => request<{ deleted: boolean }>(`/api/projects/${encodeURIComponent(id)}`, { method: "DELETE" }),
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
  },

  experiments: {
    list: (project: string) => request<ExperimentResult[]>(`${p(project)}/experiments`),
    report: (project: string) => request<EvaluationReport>(`${p(project)}/evaluation/report`),
    reportSummary: (project: string) => request<Record<string, EvalSummaryMetric>>(`${p(project)}/evaluation/report/summary`),
  },

  training: {
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
           history: { role: "user" | "assistant"; content: string }[] = [], user_context: Record<string, string> = {}) =>
      request<{ response: string; adapter: string | null; rag_used: boolean; rag_chunks: string[] }>(`${p(project)}/chat`, {
        method: "POST",
        body: JSON.stringify({ message, adapter, rag, system_prompt, history, user_context }),
      }),
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
  },
};
