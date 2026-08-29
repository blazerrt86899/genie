# Genie

> Your wish, fulfilled — a multi-agent AI orchestration platform.

Genie decomposes a user task into specialist agent workflows (web search, RAG,
calendar, task creation) via a LangGraph supervisor and synthesises a unified,
streamed response. See [`CLAUDE.md`](./CLAUDE.md) for the full architecture and
phase roadmap.

**Status:** scaffold complete — both apps boot and talk to each other. Feature
work starts at Phase 1 (`CLAUDE.md` §15).

```
Next.js 14 UI  ──HTTP/SSE──▶  FastAPI  ──▶  LangGraph supervisor  ──▶  agents  ──▶  synthesiser
                                  │
                          Redis (L1)  +  Supabase Postgres / pgvector (L2)
```

## Repository layout

| Path | What |
|------|------|
| `backend/` | FastAPI + LangGraph. Package manager: **uv**. |
| `frontend/` | Next.js 14 App Router. Package manager: **npm**. |
| `scripts/setup_supabase.sql` | One-time DB setup — extensions, hybrid-search functions, indexes, RLS. |
| `docker-compose.yml` | Local Redis + LocalStack (Postgres comes from the Supabase CLI). |
| `infrastructure/` | Terraform (Phase 4 — placeholder). |

## Quickstart (local dev)

### 0. Prerequisites

```bash
brew install uv                     # Python package manager
uv python install 3.12
npm i -g supabase                   # or: brew install supabase/tap/supabase
```

### 1. Infrastructure

```bash
supabase start                      # Postgres + pgvector on :54322, Studio :54323
docker compose up -d                # Redis :6379, LocalStack :4566

# one-time: create the `genie` schema + hybrid-search functions (in the default `postgres` db)
docker exec -i supabase_db_server psql -U postgres -d postgres < scripts/setup_supabase.sql
```

Genie's tables live in a dedicated **`genie` schema** of the `postgres`
database, so they show up in Supabase Studio (schema switcher, top-left) and
don't collide with anything else in the local stack.

### 2. Backend

```bash
cd backend
uv sync --extra dev                  # .venv + requirements.txt + requirements-dev.txt
cp ../.env.example .env
uv run alembic upgrade head          # creates users / conversations / messages
uv run uvicorn "app.main:create_app" --factory --reload
```

- http://localhost:8000/health  · /health/ready · /docs

### 3. Frontend

```bash
cd frontend
npm install

# Clerk auth (keys are managed by the Clerk CLI):
npm install -g clerk          # or brew install clerk/stable/clerk
clerk auth login
clerk init --app app_3Ia08IpcDiBIMwI1FykjqEgLCMm   # writes .env.local
clerk doctor                  # verify

npm run dev                   # http://localhost:3000
```

Open http://localhost:3000 → `/` redirects to `/chat`, which requires sign-in
(Clerk). Sign up via the sidebar. The sidebar also shows a live **backend
connected** dot. See `frontend/README.md` for details.

## Verify

| Check | Expected |
|-------|----------|
| `curl localhost:8000/health` | `{"status":"ok"}` |
| `curl localhost:8000/health/ready` | `redis` + `database` both `ok` |
| `cd backend && uv run pytest` | green |
| `cd backend && uv run ruff check .` | clean |
| `cd frontend && npm run build` | succeeds |
| Visit `/chat` signed out | redirects to `/sign-in` |
| Sign up, then visit `/chat`, send a message | your message + a placeholder reply |
| Visit `/tasks` | three empty Kanban columns |

## What's stubbed

Most backend modules raise `NotImplementedError` / return `501` until their phase
(`CLAUDE.md` §15). The scaffold provides the full directory tree, config,
health/readiness, DB models + first migration, the LangGraph checkpointer wiring,
the SSE event contract, and the Next.js shell.
