# Control-plane API image. Demo/onboarding only — GPU training still runs on
# the host venv (see README.md); this image never ships torch/CUDA, so chat
# only works here through a remote provider (Ollama/OpenAI/Anthropic-compatible,
# see the Providers page), not a locally-loaded LoRA adapter.
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY api/ ./api/
COPY rag/ ./rag/
COPY evaluation/ ./evaluation/
COPY inference/ ./inference/
COPY scripts/ ./scripts/
COPY training/ ./training/

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -fsS http://localhost:8000/api/ready || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
