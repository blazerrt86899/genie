# Genie API container (CLAUDE.md §3 — ECS Fargate, multi-worker in prod).
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install uv (used only to resolve/install deps into the system env).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY requirements.txt .
RUN uv pip install --system -r requirements.txt

COPY . .

EXPOSE 8000

# Multi-worker Gunicorn with Uvicorn workers.
CMD ["gunicorn", "app.main:create_app()", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "4", \
     "--timeout", "120"]
