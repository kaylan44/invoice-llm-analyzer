# FastAPI backend image (Railway builds this file automatically: it sits at the repo root).
# Only the invoice-api workspace member is installed: no Faker, no WeasyPrint, no evals.
#
#   docker build -t invoice-api .
#   docker run --rm -p 8000:8000 --env-file .env invoice-api

FROM python:3.12-slim

# uv pinned to the version used in development (https://docs.astral.sh/uv/guides/integration/docker/)
COPY --from=ghcr.io/astral-sh/uv:0.13.10 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 1. Dependencies only, from the lockfile: this layer is rebuilt only when they change.
#    The workspace metadata (root and member pyproject files) is needed to read uv.lock.
COPY pyproject.toml uv.lock ./
COPY api/pyproject.toml api/README.md api/
COPY evals/pyproject.toml evals/README.md evals/
RUN uv sync --frozen --package invoice-api --no-install-workspace

# 2. The application code, installed as a regular (non-editable) package.
COPY api/src api/src
RUN uv sync --frozen --package invoice-api --no-editable

# Run as an unprivileged user; uploads go to /app/storage until Supabase Storage replaces it.
RUN useradd --create-home app && mkdir -p /app/storage && chown app /app/storage
USER app
ENV PATH="/app/.venv/bin:$PATH" \
    STORAGE_DIR=/app/storage

EXPOSE 8000
# Railway injects PORT; 8000 locally. exec: uvicorn becomes PID 1 and receives stop signals.
CMD ["sh", "-c", "exec uvicorn invoice_api.app:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
