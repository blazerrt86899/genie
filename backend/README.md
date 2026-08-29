# Genie Backend

FastAPI + LangGraph orchestration layer. See root `CLAUDE.md` for the full spec.

## Setup (uv)

```bash
cd backend
uv sync --extra dev             # creates .venv, installs requirements.txt + requirements-dev.txt
cp ../.env.example .env         # local defaults target the Supabase CLI + docker-compose stack
```

> Dependencies live in `requirements.txt` / `requirements-dev.txt`. `pyproject.toml`
> pulls them in dynamically, so `uv sync` / `uv run` stay in sync with those files.
> Plain pip works too: `pip install -r requirements.txt -r requirements-dev.txt`.

Bring up infra from the repo root first:

```bash
supabase start                   # Postgres + pgvector on :54322
docker compose up -d             # redis :6379, localstack :4566
docker exec supabase_db_server psql -U postgres -c "CREATE DATABASE genie;"
docker exec -i supabase_db_server psql -U postgres -d genie < ../scripts/setup_supabase.sql
```

## Database migrations (app tables only — never checkpointer tables)

```bash
uv run alembic revision --autogenerate -m "users, conversations, messages"   # first time
uv run alembic upgrade head
```

## Run

```bash
uv run uvicorn "app.main:create_app" --factory --reload
```

- Liveness:  `curl localhost:8000/health`
- Readiness: `curl localhost:8000/health/ready`   (checks Redis + DB)
- API docs:  http://localhost:8000/docs

## Test / lint

```bash
uv run pytest
uv run ruff check .
```

## Layout

`app/` — see `CLAUDE.md` §5. Most modules are stubs that raise
`NotImplementedError` / return `501` until their phase (§15).
