"""Pydantic request/response models for the model-building console API."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class DatasetExample(BaseModel):
    id: str
    file: str
    index: int
    messages: list[Message]


class DatasetCategorySummary(BaseModel):
    category: str
    files: list[str]
    example_count: int


class AddExampleRequest(BaseModel):
    file: str
    messages: list[Message]


class UpdateExampleRequest(BaseModel):
    messages: list[Message]


class ValidationFinding(BaseModel):
    file: str
    line: int
    level: str
    message: str


class NearDuplicatePair(BaseModel):
    file_a: str
    line_a: int
    file_b: str
    line_b: int
    similarity: float


class SplitLeak(BaseModel):
    train_ref: str
    split_file: str
    split_ref: str


class ValidationResult(BaseModel):
    total_examples: int
    total_files: int
    errors: int
    warnings: int
    findings: list[ValidationFinding]
    near_duplicates: list[NearDuplicatePair] = []
    near_duplicate_scan_skipped: bool = False
    split_leaks: list[SplitLeak] = []


class PrepareDatasetRequest(BaseModel):
    version: str
    seed: int = 42


class PrepareDatasetResult(BaseModel):
    version: str
    train: int
    validation: int
    test: int


class CurrentDatasetVersion(BaseModel):
    version: str | None  # None if data/VERSION doesn't exist yet (never prepared)
    train: int
    validation: int
    test: int


class DuplicateExample(BaseModel):
    file: str
    line: int


class DeduplicateResult(BaseModel):
    dry_run: bool
    total_before: int
    total_after: int
    removed: int
    removed_by_file: dict[str, int]
    duplicates: list[DuplicateExample] = []  # populated when dry_run=True: what *would* be removed


class DatasetStats(BaseModel):
    total_examples: int
    by_category: dict[str, int]
    char_length_mean: float
    char_length_p95: float
    char_length_max: int
    exact_duplicates: int


class ExperimentResult(BaseModel):
    experiment_id: str
    config_path: str
    notes: str | None = None
    dataset_version: str | None = None
    base_model: str | None = None
    lora: dict[str, Any] | None = None
    train_loss: float | None = None
    eval_loss: float | None = None
    train_duration_minutes: float | None = None
    peak_vram_mb: float | None = None
    adapter_size_mb: float | None = None
    output_dir: str | None = None


class TrainingConfigSummary(BaseModel):
    filename: str
    experiment_id: str
    notes: str | None = None
    base_model: str
    lora_r: int
    dataset_version: str
    output_dir: str
    has_result: bool


class StartTrainingRequest(BaseModel):
    config_filename: str
    resume: bool = False


class StartPipelineRequest(BaseModel):
    config_filename: str
    dataset_version: str
    resume: bool = False


class StartSweepRequest(BaseModel):
    dataset_version: str
    resume: bool = False


class CreateConfigRequest(BaseModel):
    name: str  # used for filename + experiment id, e.g. "r24_lr1e4"
    notes: str = ""
    dataset_version: str
    lora_r: int = 16
    lora_alpha: int | None = None  # defaults to 2*r if omitted
    lora_dropout: float = 0.05
    epochs: int = 2
    learning_rate: float = 0.0002
    batch_size: int = 1
    gradient_accumulation_steps: int = 8
    warmup_steps: int = 5


class TrainingMetricPoint(BaseModel):
    step: int
    epoch: float | None = None
    loss: float | None = None
    eval_loss: float | None = None
    learning_rate: float | None = None


class ModelPreflight(BaseModel):
    model: str
    ready: bool
    accessible: bool
    architecture: str | None = None
    parameter_count: int | None = None
    estimated_download_gb: float | None = None
    estimated_vram_gb: float | None = None
    available_vram_gb: float | None = None
    cuda_available: bool
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    technical_detail: str | None = None


class JobStatus(BaseModel):
    job_id: str
    kind: Literal["training", "evaluation", "reindex", "pipeline", "sweep"]
    status: Literal["running", "completed", "failed", "stopped"]
    config_filename: str | None = None
    started_at: str
    finished_at: str | None = None
    return_code: int | None = None
    log_tail: list[str] = []
    result: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    suggestion: str | None = None


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    adapter: str | None = None  # e.g. "experiment_003", or None for base model
    system_prompt: str | None = None
    max_new_tokens: int = Field(default=400, ge=1, le=1024)
    rag: bool = False
    history: list[ChatTurn] = Field(default_factory=list, max_length=12)
    user_context: dict[Annotated[str, Field(max_length=80)], Annotated[str, Field(max_length=1000)]] = Field(default_factory=dict, max_length=10)


class SystemHealth(BaseModel):
    ok: bool
    torch_cuda: dict[str, Any]
    packages: list[dict[str, Any]]
    gpu: dict[str, Any] | None
    disk: dict[str, Any]
    ollama: dict[str, Any]


class BenchmarkChecks(BaseModel):
    expect_json: bool = False
    expect_keys: list[str] = Field(default_factory=list)
    max_chars: int = Field(ge=1, le=100000)
    expect_plain_text: bool = False


class BenchmarkCase(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
    category: str = Field(min_length=1, max_length=100)
    user: str = Field(min_length=1, max_length=20000)
    checks: BenchmarkChecks
    review: list[Annotated[str, Field(min_length=1, max_length=1000)]] = Field(min_length=1, max_length=20)


class ChatResponse(BaseModel):
    response: str
    adapter: str | None
    rag_used: bool = False
    rag_chunks: list[str] = []
    execution_id: str | None = None


class RagSearchRequest(BaseModel):
    query: str
    top_k: int = 3


class RagSearchResult(BaseModel):
    chunk_id: str
    doc_id: str
    category: str
    text: str
    score: float


RagCategory = Literal["methods", "research", "product", "other"]


class RagDocumentSummary(BaseModel):
    filename: str
    category: str
    size_bytes: int
    char_count: int
    preview: str
    reindex_job_id: str | None = None  # set when this write auto-triggered a reindex


class RagDocumentCreate(BaseModel):
    filename: str
    category: RagCategory = "other"
    content: str


class RagReindexResult(BaseModel):
    n_chunks: int
    n_documents: int


class Project(BaseModel):
    """A project is a fully isolated workspace — its own dataset, RAG documents,
    training configs, adapters and experiments, all under projects/<id>/. Picking
    a project is meant to feel like switching accounts: nothing is shared with
    any other project except the code itself (see api/routes/projects.py)."""

    id: str  # filesystem-safe slug, also the unique key — e.g. "openagent-demo"
    base_model: str  # HF repo id used for training/inference in this project
    label: str
    project_type: Literal["general", "agent", "developer", "business"] = "general"
    purpose: str = "Assistant généraliste"
    output_mode: Literal["natural", "json", "flexible"] = "natural"
    ollama_equivalent: str | None = None
    inference_model: str | None = None
    added_at: str
    dataset_examples: int = 0
    rag_documents: int = 0
    experiment_count: int = 0


class CreateProjectRequest(BaseModel):
    id: str
    base_model: str
    label: str | None = None
    project_type: Literal["general", "agent", "developer", "business"] = "general"
    purpose: str = Field(min_length=3, max_length=2000)
    output_mode: Literal["natural", "json", "flexible"] = "natural"
    system_prompt: str | None = Field(default=None, max_length=12000)
    ollama_equivalent: str | None = None


class UpdateInferenceRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200)


class ProjectSettings(BaseModel):
    id: str
    label: str
    project_type: Literal["general", "agent", "developer", "business"]
    purpose: str
    output_mode: Literal["natural", "json", "flexible"]
    base_model: str
    inference_model: str
    system_prompt: str
    max_assistant_chars: int


class UpdateProjectSettingsRequest(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    project_type: Literal["general", "agent", "developer", "business"]
    purpose: str = Field(min_length=3, max_length=2000)
    output_mode: Literal["natural", "json", "flexible"]
    inference_model: str = Field(min_length=1, max_length=200)
    system_prompt: str = Field(min_length=1, max_length=12000)
    max_assistant_chars: int = Field(ge=100, le=100000)
