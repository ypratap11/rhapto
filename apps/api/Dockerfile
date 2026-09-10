# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /app
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY apps/api/src ./src
COPY apps/api/alembic.ini ./alembic.ini
COPY apps/api/alembic ./alembic
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"

# API: migrations then uvicorn.
FROM base AS api
EXPOSE 8000
CMD ["sh", "-c", "rhapto db upgrade && uvicorn rhapto.api.app:app --host 0.0.0.0 --port 8000"]

# Heavy layer shared by worker and cli: LibreOffice for PDF and the embedding model.
FROM base AS heavy
RUN apt-get update \
    && apt-get install -y --no-install-recommends libreoffice-writer fonts-liberation \
    && rm -rf /var/lib/apt/lists/*
ENV FASTEMBED_CACHE_PATH=/models
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"

FROM heavy AS worker
CMD ["arq", "rhapto.worker.main.WorkerSettings"]

FROM heavy AS cli
WORKDIR /work
ENTRYPOINT ["rhapto"]
CMD ["--help"]
