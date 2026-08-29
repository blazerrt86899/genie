# CLAUDE.md — Genie Multi-Agent Platform

> This file is the authoritative reference for Claude Code working inside the Genie repository.
> Read this fully before writing, editing, or refactoring anything. Every decision here has a reason.
> When in doubt: ask the CLAUDE.md first, then the codebase, then the user.

---

## 1. Project Identity

**Name**: Genie
**Tagline**: "Your wish, fulfilled" — a multi-agent AI orchestration platform that decomposes any user task into specialist agent workflows and synthesises a unified response.

**Core Loop**:
```
User message → FastAPI → LangGraph Supervisor → [parallel specialist agents] → Synthesiser → SSE stream → Next.js UI
```

**What Genie is NOT**:
- Not a simple chatbot wrapper around a single LLM call
- Not a rigid, rule-based automation pipeline
- Not a monolith — agents are independently testable, replaceable units

---

## 2. Architecture Layers

```
┌─────────────────────────────────────────────────────────┐
│  CLIENT  │  Next.js 15 (App Router) + Tailwind CSS       │
│          │  Chat UI · Agent Activity · Task Board         │
└──────────┬──────────────────────────────────────────────┘
           │ HTTPS / SSE
┌──────────▼──────────────────────────────────────────────┐
│  API     │  FastAPI (Python 3.12) + Uvicorn/Gunicorn      │
│          │  Clerk Auth · Rate Limiting · SSE · REST        │
└──────────┬──────────────────────────────────────────────┘
           │ Internal
┌──────────▼──────────────────────────────────────────────┐
│  ORCH    │  LangGraph (supervisor pattern)                 │
│          │  GenieState → Supervisor → Agents → Synthesiser │
└──────────┬──────────────────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────┐
│  MEMORY  │  Redis (L1, TTL 2h) + Supabase PostgreSQL (L2) │
│          │  pgvector · tsvector · Hybrid Search            │
└──────────┬──────────────────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────┐
│  EXTERN  │  OpenAI / Anthropic · Tavily Search            │
│          │  Google Calendar API · AWS SQS / S3             │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Full Tech Stack

### Backend
| Component | Choice | Version / Notes |
|-----------|--------|-----------------|
| Language | Python | 3.12+ |
| Framework | FastAPI | Latest stable |
| ASGI Server | Uvicorn + Gunicorn | Multi-worker in prod |
| Orchestration | LangGraph | Supervisor pattern, `astream_events v2` |
| LLM Routing | OpenAI `gpt-4o-2024-08-06` | Pin the version in prod |
| Embeddings | OpenAI `text-embedding-3-small` | 1536 dims |
| Task Queue | AWS SQS | Standard queue, idempotent consumers |
| Background Worker | Python SQS consumer | Separate ECS service |
| Auth | **Clerk** | Hosted auth, webhook sync to DB, JWKS-verified JWT in FastAPI |
| Observability | LangSmith + AWS X-Ray | Trace every graph run |
| Circuit Breaker | `tenacity` | Exponential backoff, 3 retries |
| Validation | Pydantic v2 | All request/response models |

### Database
| Component | Choice | Notes |
|-----------|--------|-------|
| Primary DB | **Supabase Cloud PostgreSQL** | Managed, pgvector + tsvector enabled |
| ORM | SQLAlchemy 2.0 (async) | For complex queries + LangGraph checkpointer |
| Supabase Client | `supabase-py` | For auth helpers, storage, realtime |
| Migrations | Alembic | Only for app tables — NOT checkpointer tables |
| Vector Search | pgvector (`vector(1536)`) | IVFFlat index, cosine ops |
| Full-Text Search | PostgreSQL tsvector | GIN index, `plainto_tsquery('english', ...)` |
| RAG Search | **Hybrid Search (RRF)** | Vector + FTS fused via Reciprocal Rank Fusion |
| Session Cache | ElastiCache Redis | TTL 2h, recent messages + rate limits |
| Checkpointer | `AsyncPostgresSaver` | LangGraph state persistence — session pool |

### Supabase Connection URLs (three modes — use the right one)
```python
# .env
# 1. Direct (for Alembic migrations, setup scripts)
DATABASE_URL_DIRECT="postgresql+asyncpg://postgres:PASSWORD@db.REF.supabase.co:5432/postgres"

# 2. Supavisor Transaction Mode (for FastAPI / API handlers — short-lived)
DATABASE_URL_POOL="postgresql+asyncpg://postgres.REF:PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres"

# 3. Supavisor Session Mode (for LangGraph AsyncPostgresSaver — needs LISTEN/NOTIFY)
DATABASE_URL_SESSION="postgresql+asyncpg://postgres.REF:PASSWORD@aws-0-REGION.pooler.supabase.com:5432/postgres"
```
**Rule**: FastAPI uses `DATABASE_URL_POOL`. LangGraph checkpointer uses `DATABASE_URL_SESSION`. Alembic uses `DATABASE_URL_DIRECT`.

**Schema**: all Genie tables (and the checkpointer tables) live in a dedicated
**`genie` Postgres schema**, never `public`. `Base.metadata = MetaData(schema="genie")`
(`db/models/base.py:DB_SCHEMA`); the async engine sets `search_path=genie,public,extensions`;
Alembic uses `version_table_schema="genie"` + an `include_name` filter so it only
ever touches the `genie` schema; `main.py` pins the checkpointer connection's
`search_path` to `genie`. `scripts/setup_supabase.sql` creates the schema.
Locally this means one shared `postgres` database, `genie`-schema isolation, and
Supabase Studio shows the tables via its schema switcher.

### Frontend
| Component | Choice | Notes |
|-----------|--------|-------|
| Framework | Next.js 15 | App Router only (no Pages Router). React 19. |
| Styling | Tailwind CSS v3 | `darkMode: "class"` + CSS-var tokens (incl. `--brand` violet→indigo) |
| Theme | `next-themes` | Global light/dark toggle (`attribute="class"`, `defaultTheme="system"`), `<ThemeProvider>` outermost in `layout.tsx` |
| State | Zustand | Global chat/task/agent state |
| Streaming | Native `EventSource` API | SSE — no third-party lib needed |
| Data Fetching | TanStack Query v5 | REST endpoints + cache invalidation |
| Auth | `@clerk/nextjs` v7 | Set up via Clerk CLI. `ClerkProvider` in `<body>`, resource-based auth in `(app)/layout.tsx`. `appearance` (`lib/clerk-appearance.ts`) binds every colour to the HSL design tokens so Clerk follows light/dark automatically (not `@clerk/ui`/`@clerk/themes` — need Tailwind v4 / Core 2). Core-3: use `<Show when="signed-in">`, not `<SignedIn>`. `<SignIn/>`/`<SignUp/>` have `fallbackRedirectUrl="/chat"`. |
| UI Components | shadcn/ui | Radix primitives, unstyled base |
| Icons | Lucide React (v1 — no brand icons; inline SVG for X/GitHub/LinkedIn) | Consistent icon set |
| Animations | Framer Motion | Agent activity + the landing hero animation |

### Infrastructure (AWS)
| Service | Role |
|---------|------|
| ECS Fargate (API) | FastAPI, 1vCPU/2GB, autoscale 2–10 |
| ECS Fargate (Worker) | SQS consumer + background tasks, 2vCPU/4GB |
| ElastiCache Redis | L1 memory cache, rate limiting |
| **Supabase Cloud** | PostgreSQL (replaces RDS) |
| S3 | Document storage + Next.js static assets |
| CloudFront | CDN over S3 + ALB |
| ALB | HTTPS termination, SSE-compatible (no WebSocket needed) |
| SQS | Memory consolidation + document ingestion jobs |
| Secrets Manager | All API keys, DB creds, JWT secrets |
| CloudWatch + X-Ray | Logs, metrics, distributed tracing |

---

## 4. Core Design Commandments

These are non-negotiable. Do not violate them. Do not find clever workarounds.

1. **Dynamic routing only** — The supervisor agent NEVER has hardcoded `if "calendar" in query` logic. Routing is always via `ChatOpenAI.with_structured_output(RouteDecision)`. LLM decides which agents to invoke.

2. **Stateless compute, stateful storage** — ECS containers hold zero durable state. All state lives in Redis (ephemeral) or Supabase (permanent). This enables autoscaling.

3. **Agent single responsibility** — Each agent does one thing. The Web Search agent does not create tasks. The Task Creator agent does not search the web. Cross-concerns go to the Synthesiser.

4. **Repository pattern everywhere** — No raw SQL or Supabase client calls inside FastAPI route handlers. All DB access goes through `app/db/repositories/`. Route handlers call services, services call repositories.

5. **Idempotent SQS consumers** — Every background job (memory consolidation, document ingestion) must be safe to run twice with the same input. Use a `processed_at` column and check before acting.

6. **Token budget enforced** — Every LangGraph run has a hard ceiling of 50,000 tokens (configurable). The supervisor checks `state.token_usage` before routing to additional agents. Silent cost overruns are a production bug.

7. **User data isolation at every layer** — The RAG retriever, memory loader, and task queries ALL include `WHERE user_id = :user_id`. This is never optional. Write a test for this.

8. **Observability from day one** — Every agent node emits a LangSmith trace. Every API request gets a `request_id` injected by middleware. Every SQS job gets a `job_id`. Logs are structured JSON.

---

## 5. Project File Structure

```
genie/
├── CLAUDE.md                          ← You are here
├── .env.example                       ← Copy to .env, never commit .env
├── docker-compose.yml                 ← Local dev: Redis, localstack
│
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/
│   │   └── versions/                  ← App table migrations only
│   │
│   └── app/
│       ├── main.py                    ← FastAPI app factory, lifespan
│       ├── config.py                  ← Settings (pydantic-settings, env vars)
│       ├── dependencies.py            ← FastAPI DI: db session, current user, redis
│       │
│       ├── api/v1/
│       │   ├── router.py
│       │   └── endpoints/
│       │       ├── webhooks.py        ← POST /webhooks/clerk (user.created/updated/deleted)
│       │       ├── users.py           ← GET /users/me (resolve Clerk token → internal user)
│       │       ├── chat.py            ← /chat (POST), /chat/{id}/stream (GET SSE)
│       │       ├── conversations.py   ← /conversations CRUD
│       │       ├── tasks.py           ← /tasks CRUD
│       │       └── documents.py       ← /documents upload + list
│       │
│       ├── agents/
│       │   ├── supervisor/
│       │   │   ├── graph.py           ← build_graph(), compile with checkpointer
│       │   │   ├── state.py           ← GenieState TypedDict
│       │   │   ├── nodes.py           ← supervisor_node(), synthesiser_node()
│       │   │   └── prompts.py         ← System prompts for supervisor
│       │   │
│       │   ├── prompt_enhancer/
│       │   │   ├── agent.py
│       │   │   └── prompts.py
│       │   │
│       │   ├── web_search/
│       │   │   ├── agent.py
│       │   │   └── tools.py           ← TavilySearchResults, WebPageFetcher
│       │   │
│       │   ├── rag/
│       │   │   ├── agent.py
│       │   │   ├── retriever.py       ← hybrid_search() calls Supabase RPC
│       │   │   └── embedder.py        ← embed_text() → text-embedding-3-small
│       │   │
│       │   ├── calendar/
│       │   │   ├── agent.py           ← interrupt_before writes
│       │   │   └── tools.py           ← Google Calendar API wrappers
│       │   │
│       │   └── task_creator/
│       │       ├── agent.py
│       │       └── schemas.py         ← ExtractedTask Pydantic model
│       │
│       ├── memory/
│       │   ├── short_term.py          ← Redis ops: recent_messages, rate_limit
│       │   ├── long_term.py           ← Supabase: user_memory hybrid search
│       │   └── manager.py             ← load_context() orchestrates L1 + L2
│       │
│       ├── db/
│       │   ├── session.py             ← Async SQLAlchemy engine + session factory
│       │   ├── models/                ← SQLAlchemy ORM models (one file per table)
│       │   └── repositories/
│       │       ├── base.py
│       │       ├── user_repo.py
│       │       ├── conversation_repo.py
│       │       ├── message_repo.py
│       │       ├── task_repo.py
│       │       ├── document_repo.py
│       │       └── memory_repo.py
│       │
│       ├── services/
│       │   ├── chat_service.py        ← Orchestrates memory load + graph run + SSE
│       │   ├── memory_service.py      ← Memory consolidation logic
│       │   └── document_service.py    ← Chunking, embedding, upsert
│       │
│       ├── workers/
│       │   ├── sqs_consumer.py        ← Polling loop, dispatch by job_type
│       │   ├── memory_consolidation.py
│       │   └── document_ingestion.py
│       │
│       └── core/
│           ├── clerk.py               ← JWKS fetch+cache, RS256 verify, get_current_user()
│           ├── clerk_api.py           ← thin Clerk Backend API client (profile enrichment)
│           ├── redis.py               ← async Redis client singleton
│           ├── streaming.py           ← SSE frame helpers (§11)
│           ├── observability.py       ← configure_tracing() — LangSmith → os.environ
│           ├── logging.py             ← structlog JSON config
│           ├── middleware.py          ← request_id injection, timing
│           └── exceptions.py          ← Custom HTTP exception classes
│
├── frontend/                          ← Next.js 15, React 19, Tailwind v3, npm
│   ├── package.json
│   ├── next.config.mjs
│   ├── tailwind.config.ts
│   ├── components.json                ← shadcn/ui conventions
│   └── src/
│       ├── middleware.ts              ← bare clerkMiddleware() + /__clerk/:path* matcher
│       ├── app/                       ← App Router pages
│       │   ├── layout.tsx             ← ThemeProvider › ClerkProvider (in <body>) › QueryProvider
│       │   ├── globals.css            ← Tailwind + light/dark CSS-var tokens + marquee keyframes
│       │   ├── page.tsx               ← Marketing landing (SiteHeader/Hero/…/Footer)
│       │   ├── sign-in/[[...sign-in]]/page.tsx   ← Clerk hosted <SignIn />
│       │   ├── sign-up/[[...sign-up]]/page.tsx   ← Clerk hosted <SignUp />
│       │   └── (app)/
│       │       ├── layout.tsx         ← auth() gate (redirect to /sign-in) + Sidebar
│       │       ├── chat/page.tsx      ← Main chat interface
│       │       └── tasks/page.tsx     ← Task board
│       │
│       ├── components/
│       │   ├── Sidebar.tsx            ← nav + BackendStatus + Clerk sign-in/user buttons
│       │   ├── BackendStatus.tsx      ← live GET /health dot (TanStack Query)
│       │   ├── landing/               ← SiteHeader, Hero, CallOrb (hero animation),
│       │   │                              ThemeToggle, LogoMarquee, HowItWorks, Features,
│       │   │                              VoiceComingSoon, CtaBand, Footer, Container, Wordmark
│       │   ├── chat/
│       │   │   ├── ChatWindow.tsx     ← Message list + input
│       │   │   ├── Message.tsx        ← Renders user/assistant messages
│       │   │   ├── AgentActivity.tsx  ← Live "web_search is thinking..." strip
│       │   │   └── StreamingDot.tsx   ← Animated typing indicator
│       │   ├── tasks/
│       │   │   ├── TaskBoard.tsx      ← Kanban: todo/in-progress/done
│       │   │   └── TaskCard.tsx
│       │   └── ui/                    ← shadcn/ui primitives (button)
│       │
│       ├── hooks/
│       │   ├── useChat.ts             ← POST /chat + SSE stream + localStorage rehydrate
│       │   └── useTasks.ts            ← TanStack Query for tasks (stub)
│       │
│       ├── providers/
│       │   ├── query-provider.tsx     ← TanStack QueryClientProvider
│       │   └── theme-provider.tsx     ← next-themes ThemeProvider
│       │
│       ├── store/
│       │   ├── chatStore.ts           ← Zustand: messages, active agents, run_id
│       │   └── taskStore.ts
│       │
│       └── lib/
│           ├── api.ts                 ← Typed fetch wrapper (injects Clerk Bearer token)
│           ├── sse.ts                 ← SSE event parser + dispatcher
│           └── clerk-appearance.ts    ← CSS-free Clerk theme (appearance prop)
│
├── infrastructure/
│   └── terraform/
│       ├── main.tf
│       ├── variables.tf
│       └── modules/
│           ├── ecs/
│           ├── elasticache/
│           ├── alb/
│           ├── sqs/
│           ├── s3/
│           └── networking/
│
└── scripts/
    ├── setup_supabase.sql             ← Run once: extensions, RLS, hybrid search functions
    ├── seed_dev.py
    └── load_test.py
```

---

## 6. Environment Variables

```bash
# .env (never commit — copy from .env.example)

# App
APP_ENV=development          # development | staging | production

# ─── Clerk Auth (backend) ────────────────────────────────────────────────────
# Get from Clerk Dashboard → API Keys
CLERK_SECRET_KEY=sk_live_...            # Never expose to frontend
CLERK_PUBLISHABLE_KEY=pk_live_...      # Also set as NEXT_PUBLIC_ in frontend
CLERK_WEBHOOK_SECRET=whsec_...         # Signing secret from Clerk Dashboard → Webhooks
CLERK_DOMAIN=YOUR_CLERK_DOMAIN         # e.g. clerk.genie.ai OR generated.clerk.accounts.dev
# Used to verify JWTs — FastAPI fetches JWKS from:
# https://{CLERK_DOMAIN}/.well-known/jwks.json

# ─── Frontend Clerk env vars (prefix NEXT_PUBLIC_) ───────────────────────────
# Add these to frontend/.env.local (or Next.js env config)
# NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_live_...
# NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
# NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
# NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL=/chat
# NEXT_PUBLIC_CLERK_AFTER_SIGN_UP_URL=/chat

# ─── Database — Supabase ─────────────────────────────────────────────────────
# Three connection strings — ALWAYS use the right one (see Section 3)
DATABASE_URL_DIRECT=         # postgresql+asyncpg://postgres:PW@db.REF.supabase.co:5432/postgres
DATABASE_URL_POOL=           # postgresql+asyncpg://postgres.REF:PW@pooler.supabase.com:6543/postgres
DATABASE_URL_SESSION=        # postgresql+asyncpg://postgres.REF:PW@pooler.supabase.com:5432/postgres
SUPABASE_URL=                # https://REF.supabase.co
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=   # Backend only — NEVER send to frontend

# ─── Redis (ElastiCache) ─────────────────────────────────────────────────────
REDIS_URL=redis://localhost:6379
JWKS_CACHE_TTL_SECONDS=3600          # How long to cache Clerk JWKS (1 hour)
CLERK_USER_CACHE_TTL_SECONDS=300     # clerk_id → internal user_id mapping cache

# ─── LLM ─────────────────────────────────────────────────────────────────────
OPENAI_API_KEY=
ANTHROPIC_API_KEY=           # For Claude-specific agent nodes
OPENAI_CHAT_MODEL=gpt-4o-2024-08-06   # ALWAYS pin the model version — never use "gpt-4o"
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

# ─── LangSmith (observability) ───────────────────────────────────────────────
# `app/core/observability.py:configure_tracing()` copies these into os.environ at
# startup — LangChain reads them from there, not from Settings. Legacy
# LANGCHAIN_* names still accepted (AliasChoices).
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=genie-prod  # or genie-dev

# ─── Search ──────────────────────────────────────────────────────────────────
TAVILY_API_KEY=

# ─── Google OAuth (Calendar agent only — not user auth) ──────────────────────
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
OAUTH_TOKEN_ENCRYPTION_KEY=  # Fernet key, 32-byte base64 (encrypt tokens in DB)

# ─── AWS ─────────────────────────────────────────────────────────────────────
AWS_REGION=ap-south-1
SQS_QUEUE_URL=
S3_BUCKET_NAME=
AWS_ACCESS_KEY_ID=            # Local dev only — use ECS IAM roles in production
AWS_SECRET_ACCESS_KEY=        # Local dev only

# ─── Limits ──────────────────────────────────────────────────────────────────
MAX_TOKENS_PER_RUN=50000
RATE_LIMIT_REQUESTS_PER_MINUTE=60
```

---

## 7. Clerk Auth Integration

### 7.1 How It Works End-to-End

```
User signs up/in on Next.js (Clerk UI)
  → Clerk issues a short-lived JWT (RS256, signed with Clerk's private key)
  → Clerk fires webhook: user.created → POST /api/v1/webhooks/clerk
  → FastAPI webhook handler inserts row into `users` table
  → Frontend attaches JWT as Bearer token on every API request
  → FastAPI dependency verifies JWT against Clerk JWKS, resolves internal user_id
  → All DB queries use internal UUID (not clerk_id)
```

**What Clerk owns**: credentials, sessions, MFA, social logins, email verification, password resets, rate limiting login attempts.

**What FastAPI owns**: business logic, all database operations, agent orchestration.

**Never build custom**: login pages, password hashing, JWT minting, refresh token rotation, session storage. Clerk handles all of this.

### 7.2 Users Table Schema

```sql
-- app/db/models/user.py → Alembic migration
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    clerk_id        VARCHAR(255) UNIQUE NOT NULL,  -- Clerk's user_id: "user_2abc123"
    email           VARCHAR(255) UNIQUE NOT NULL,
    full_name       VARCHAR(255),
    avatar_url      TEXT,
    email_verified  BOOLEAN NOT NULL DEFAULT false,
    token_budget    INTEGER NOT NULL DEFAULT 100000,  -- per-user LLM token quota
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at  TIMESTAMPTZ,
    metadata        JSONB NOT NULL DEFAULT '{}'
    -- NO password_hash — Clerk owns credentials
    -- NO is_active — Clerk manages account lifecycle
    -- NO refresh_token — Clerk manages sessions
);

CREATE INDEX ON users (clerk_id);  -- Frequent lookup by clerk_id on every request
CREATE INDEX ON users (email);
```

**FK design rule**: All other tables (`conversations`, `tasks`, `messages`, `documents`, etc.) reference `users.id` (UUID), never `users.clerk_id`. The `clerk_id` mapping only happens once in `get_current_user()`.

### 7.3 JWT Verification Dependency (FastAPI)

```python
# app/core/clerk.py
import json
import httpx
import jwt
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config import settings
from app.core.redis import get_redis

security_scheme = HTTPBearer()

async def _get_jwks(redis) -> dict:
    """Fetch Clerk's public JWKS, cached in Redis for JWKS_CACHE_TTL_SECONDS."""
    cached = await redis.get("clerk:jwks")
    if cached:
        return json.loads(cached)
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://{settings.CLERK_DOMAIN}/.well-known/jwks.json",
            timeout=5.0,
        )
        resp.raise_for_status()
    jwks = resp.json()
    await redis.setex("clerk:jwks", settings.JWKS_CACHE_TTL_SECONDS, json.dumps(jwks))
    return jwks

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security_scheme),
    db: AsyncSession = Depends(get_db),
    redis = Depends(get_redis),
) -> User:
    token = credentials.credentials

    # 1. Verify the Clerk JWT
    try:
        jwks = await _get_jwks(redis)
        payload = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            options={"verify_aud": False},  # Clerk omits 'aud' by default
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    clerk_id: str = payload.get("sub")
    if not clerk_id:
        raise HTTPException(status_code=401, detail="Missing subject claim")

    # 2. Resolve clerk_id → internal user_id (cached in Redis)
    cache_key = f"user_by_clerk:{clerk_id}"
    cached_user_id = await redis.get(cache_key)

    if cached_user_id:
        user = await UserRepository(db).get_by_id(UUID(cached_user_id.decode()))
    else:
        user = await UserRepository(db).get_by_clerk_id(clerk_id)
        if not user:
            # Race condition: webhook hasn't arrived yet — auto-create from token
            user = await UserRepository(db).create_from_clerk_token(payload)
        await redis.setex(cache_key, settings.CLERK_USER_CACHE_TTL_SECONDS, str(user.id))

    # 3. Update last_active_at (fire-and-forget)
    await UserRepository(db).touch_last_active(user.id)
    return user
```

### 7.4 Clerk Webhook Handler

The webhook is how your `users` table stays in sync with Clerk. **Always verify the Svix signature** — never process unsigned webhooks.

```python
# app/api/v1/endpoints/webhooks.py
from svix.webhooks import Webhook, WebhookVerificationError
from app.config import settings

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

@router.post("/clerk", status_code=200)
async def clerk_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    payload = await request.body()
    svix_headers = {
        "svix-id":        request.headers.get("svix-id", ""),
        "svix-timestamp": request.headers.get("svix-timestamp", ""),
        "svix-signature": request.headers.get("svix-signature", ""),
    }

    # Verify webhook authenticity
    try:
        wh = Webhook(settings.CLERK_WEBHOOK_SECRET)
        event = wh.verify(payload, svix_headers)
    except WebhookVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type: str = event.get("type")
    data: dict = event.get("data", {})

    repo = UserRepository(db)

    if event_type == "user.created":
        await repo.create_from_clerk(data)

    elif event_type == "user.updated":
        await repo.update_from_clerk(data)

    elif event_type == "user.deleted":
        # Soft delete — preserves conversations for data integrity
        await repo.soft_delete_by_clerk_id(data["id"])

    return {"received": True}
```

### 7.5 UserRepository Clerk Helpers

```python
# app/db/repositories/user_repo.py

async def create_from_clerk(self, clerk_data: dict) -> User:
    """Called by webhook on user.created."""
    primary_email = next(
        (e for e in clerk_data["email_addresses"] if e["id"] == clerk_data.get("primary_email_address_id")),
        clerk_data["email_addresses"][0]
    )
    user = User(
        clerk_id=clerk_data["id"],
        email=primary_email["email_address"],
        full_name=f"{clerk_data.get('first_name') or ''} {clerk_data.get('last_name') or ''}".strip() or None,
        avatar_url=clerk_data.get("image_url"),
        email_verified=primary_email.get("verification", {}).get("status") == "verified",
    )
    self.db.add(user)
    await self.db.commit()
    await self.db.refresh(user)
    return user

async def create_from_clerk_token(self, jwt_payload: dict) -> User:
    """Fallback: called by get_current_user if webhook hasn't arrived yet."""
    user = User(
        clerk_id=jwt_payload["sub"],
        email=jwt_payload.get("email", f"{jwt_payload['sub']}@placeholder.clerk"),
        full_name=jwt_payload.get("name"),
        avatar_url=jwt_payload.get("image_url"),
        email_verified=bool(jwt_payload.get("email_verified")),
    )
    self.db.add(user)
    await self.db.commit()
    await self.db.refresh(user)
    return user

async def update_from_clerk(self, clerk_data: dict) -> None:
    """Called by webhook on user.updated."""
    primary_email = next(
        (e for e in clerk_data["email_addresses"] if e["id"] == clerk_data.get("primary_email_address_id")),
        clerk_data["email_addresses"][0]
    )
    await self.db.execute(
        update(User)
        .where(User.clerk_id == clerk_data["id"])
        .values(
            email=primary_email["email_address"],
            full_name=f"{clerk_data.get('first_name') or ''} {clerk_data.get('last_name') or ''}".strip() or None,
            avatar_url=clerk_data.get("image_url"),
            updated_at=datetime.utcnow(),
        )
    )
    await self.db.commit()

async def soft_delete_by_clerk_id(self, clerk_id: str) -> None:
    """Called by webhook on user.deleted. Soft delete preserves conversation history."""
    await self.db.execute(
        update(User)
        .where(User.clerk_id == clerk_id)
        .values(clerk_id=f"deleted_{clerk_id}", email=f"deleted_{clerk_id}@deleted.invalid")
    )
    await self.db.commit()
```

### 7.6 Frontend: ClerkProvider + Middleware

Setup is done with the **Clerk CLI** (`clerk auth login` → `clerk init --app
app_3Ia08IpcDiBIMwI1FykjqEgLCMm`), which links the repo to the Clerk app and
writes `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` + `CLERK_SECRET_KEY` to
`frontend/.env.local`. Frontend runs `@clerk/nextjs` **v7** (needs Next 15+).

`ClerkProvider` goes **inside `<body>`**, not wrapping `<html>`. Theme the
prebuilt components with the CSS-free `appearance` prop
(`src/lib/clerk-appearance.ts`) — the `@clerk/ui` shadcn theme needs Tailwind v4
and this project is on v3, so it renders unstyled if used.

```tsx
// frontend/src/app/layout.tsx
import { ClerkProvider } from '@clerk/nextjs'
import { clerkAppearance } from '@/lib/clerk-appearance'

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <ClerkProvider appearance={clerkAppearance}>
          <QueryProvider>{children}</QueryProvider>
        </ClerkProvider>
      </body>
    </html>
  )
}
```

Clerk v7 favours **resource-based auth checks** over middleware path-matching
(`createRouteMatcher` is deprecated). Middleware just enables `auth()` + the
`/__clerk/*` auto-proxy; the gate lives in the route group layout:

```tsx
// frontend/src/middleware.ts
import { clerkMiddleware } from '@clerk/nextjs/server'
export default clerkMiddleware()
export const config = {
  matcher: [
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    '/(api|trpc)(.*)',
    '/__clerk/:path*',   // Clerk auto-proxy — keep after the API matcher
  ],
}

// frontend/src/app/(app)/layout.tsx  — the actual protection
import { auth } from '@clerk/nextjs/server'
import { redirect } from 'next/navigation'
export default async function AppLayout({ children }) {
  const { userId } = await auth()          // v7: auth() is async
  if (!userId) redirect('/sign-in')
  return <>{children}</>
}
```

```typescript
// frontend/src/app/sign-in/[[...sign-in]]/page.tsx
import { SignIn } from '@clerk/nextjs'
export default function SignInPage() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <SignIn />
    </div>
  )
}

// frontend/src/app/sign-up/[[...sign-up]]/page.tsx
import { SignUp } from '@clerk/nextjs'
export default function SignUpPage() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <SignUp />
    </div>
  )
}
```

```typescript
// frontend/src/lib/api.ts — inject Clerk JWT on every request
import { auth } from '@clerk/nextjs/server'   // Server Components / Route Handlers

export async function serverFetch(path: string, options: RequestInit = {}) {
  const { getToken } = await auth()
  const token = await getToken()
  return fetch(`${process.env.NEXT_PUBLIC_API_URL}${path}`, {
    ...options,
    headers: { ...options.headers, Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
  })
}

// For 'use client' components — use useAuth() hook:
// const { getToken } = useAuth()
// const token = await getToken()
// then pass token to your fetch wrapper
```

### 7.7 Redis Keys Added by Clerk Integration

```
clerk:jwks                    → cached JWKS JSON (TTL: JWKS_CACHE_TTL_SECONDS = 3600)
user_by_clerk:{clerk_id}      → internal user UUID string (TTL: CLERK_USER_CACHE_TTL_SECONDS = 300)
```

These replace the old `session:{user_id}` JWT refresh token key. All other Redis keys (`recent_messages:*`, `rate_limit:*`) are unchanged.

### 7.8 Clerk Dashboard Setup Checklist

Before running the app:
- [ ] Create Clerk application at dashboard.clerk.com
- [ ] Copy `CLERK_SECRET_KEY`, `CLERK_PUBLISHABLE_KEY` to `.env`
- [ ] In Clerk Dashboard → Webhooks → Add endpoint: `https://your-domain.com/api/v1/webhooks/clerk`
- [ ] Subscribe to events: `user.created`, `user.updated`, `user.deleted`
- [ ] Copy webhook signing secret to `CLERK_WEBHOOK_SECRET`
- [ ] In Clerk Dashboard → Domains: set your app's domain
- [ ] Install `svix` Python package: `pip install svix`
- [ ] Install `@clerk/nextjs` frontend package: `npm install @clerk/nextjs`

---

## 8. Supabase Setup (One-Time)

Run `scripts/setup_supabase.sql` once against the target's **`postgres`** database
(`docker exec -i supabase_db_server psql -U postgres -d postgres < scripts/setup_supabase.sql`).
It creates the **`genie` schema** first, then everything below lands in it
(`SET search_path = genie, …`; the RPCs also pin their own `search_path`). All
Genie objects — app tables, checkpointer tables, RPCs — live in `genie`, never `public`.

### 8.1 Required Extensions
```sql
CREATE EXTENSION IF NOT EXISTS vector;       -- pgvector
CREATE EXTENSION IF NOT EXISTS pg_trgm;      -- trigram (FTS support)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";  -- uuid_generate_v4()
```

### 8.2 Core Tables (run via Alembic after this)
Alembic manages schema for: `users`, `conversations`, `messages`, `tasks`, `documents`, `document_chunks`, `user_memory`, `agent_runs`, `oauth_credentials`.

**DO NOT** add LangGraph checkpointer tables to Alembic. They are created by:
```python
await checkpointer.setup()  # called once in FastAPI lifespan startup
```

### 8.3 Hybrid Search Function — document_chunks
> Lives in the `genie` schema. To call it via `supabase.rpc(...)` (PostgREST),
> add `genie` to the project's exposed schemas (Supabase: *API → Exposed schemas*,
> or `PGRST_DB_SCHEMAS`); otherwise call it over SQLAlchemy as
> `SELECT * FROM genie.hybrid_search_documents(...)`. Phase 2 decision.
```sql
-- Created by setup_supabase.sql (CREATE OR REPLACE FUNCTION genie.hybrid_search_documents ...)
-- Called via: supabase.rpc('hybrid_search_documents', {...})

CREATE OR REPLACE FUNCTION hybrid_search_documents(
  query_text      TEXT,
  query_embedding vector(1536),
  target_user_id  UUID,
  match_count     INT DEFAULT 10,
  fts_weight      FLOAT DEFAULT 1.0,
  semantic_weight FLOAT DEFAULT 1.0,
  rrf_k           INT DEFAULT 50
)
RETURNS TABLE (
  id          UUID,
  content     TEXT,
  metadata    JSONB,
  document_id UUID,
  score       FLOAT
)
LANGUAGE sql
STABLE
AS $$
  WITH full_text AS (
    SELECT
      dc.id,
      ROW_NUMBER() OVER (
        ORDER BY ts_rank_cd(dc.fts_content, plainto_tsquery('english', query_text)) DESC
      ) AS rank_ix
    FROM document_chunks dc
    WHERE dc.user_id = target_user_id
      AND dc.fts_content @@ plainto_tsquery('english', query_text)
    LIMIT LEAST(match_count, 30) * 2
  ),
  semantic AS (
    SELECT
      dc.id,
      ROW_NUMBER() OVER (
        ORDER BY dc.embedding <=> query_embedding
      ) AS rank_ix
    FROM document_chunks dc
    WHERE dc.user_id = target_user_id
    ORDER BY dc.embedding <=> query_embedding
    LIMIT LEAST(match_count, 30) * 2
  )
  SELECT
    dc.id,
    dc.content,
    dc.metadata,
    dc.document_id,
    (
      COALESCE(1.0 / (rrf_k + ft.rank_ix), 0.0) * fts_weight +
      COALESCE(1.0 / (rrf_k + s.rank_ix), 0.0) * semantic_weight
    ) AS score
  FROM document_chunks dc
  FULL OUTER JOIN full_text ft ON dc.id = ft.id
  FULL OUTER JOIN semantic s   ON dc.id = s.id
  WHERE dc.user_id = target_user_id
  ORDER BY score DESC
  LIMIT match_count;
$$;
```

### 8.4 Hybrid Search Function — user_memory
```sql
CREATE OR REPLACE FUNCTION hybrid_search_memories(
  query_text      TEXT,
  query_embedding vector(1536),
  target_user_id  UUID,
  match_count     INT DEFAULT 5,
  fts_weight      FLOAT DEFAULT 0.5,
  semantic_weight FLOAT DEFAULT 1.5,
  rrf_k           INT DEFAULT 50
)
RETURNS TABLE (
  id         UUID,
  content    TEXT,
  importance FLOAT,
  score      FLOAT
)
LANGUAGE sql
STABLE
AS $$
  -- Same RRF pattern as hybrid_search_documents
  -- Note: semantic_weight is higher for memory (meaning > keywords)
  WITH full_text AS (
    SELECT id,
      ROW_NUMBER() OVER (
        ORDER BY ts_rank_cd(fts_content, plainto_tsquery('english', query_text)) DESC
      ) AS rank_ix
    FROM user_memory
    WHERE user_id = target_user_id
      AND fts_content @@ plainto_tsquery('english', query_text)
    LIMIT LEAST(match_count, 20) * 2
  ),
  semantic AS (
    SELECT id,
      ROW_NUMBER() OVER (ORDER BY embedding <=> query_embedding) AS rank_ix
    FROM user_memory
    WHERE user_id = target_user_id
    ORDER BY embedding <=> query_embedding
    LIMIT LEAST(match_count, 20) * 2
  )
  SELECT
    um.id,
    um.content,
    um.importance,
    (
      COALESCE(1.0 / (rrf_k + ft.rank_ix), 0.0) * fts_weight +
      COALESCE(1.0 / (rrf_k + s.rank_ix), 0.0) * semantic_weight
    ) AS score
  FROM user_memory um
  FULL OUTER JOIN full_text ft ON um.id = ft.id
  FULL OUTER JOIN semantic s   ON um.id = s.id
  WHERE um.user_id = target_user_id
  ORDER BY score DESC
  LIMIT match_count;
$$;
```

### 8.5 Required Indexes
```sql
-- pgvector indexes (run after table creation)
CREATE INDEX ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX ON user_memory     USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);

-- Full-text search indexes
CREATE INDEX ON document_chunks USING gin(fts_content);
CREATE INDEX ON user_memory     USING gin(fts_content);

-- Standard query indexes
CREATE INDEX ON messages         (conversation_id, created_at);
CREATE INDEX ON document_chunks  (document_id, user_id);
CREATE INDEX ON tasks            (user_id, status, created_at);
```

### 8.6 fts_content Auto-Population Trigger
```sql
-- Automatically populate tsvector column when content is inserted/updated
CREATE OR REPLACE FUNCTION update_fts_content()
RETURNS TRIGGER AS $$
BEGIN
  NEW.fts_content := to_tsvector('english', COALESCE(NEW.content, ''));
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_document_chunks_fts
  BEFORE INSERT OR UPDATE OF content ON document_chunks
  FOR EACH ROW EXECUTE FUNCTION update_fts_content();

CREATE TRIGGER update_user_memory_fts
  BEFORE INSERT OR UPDATE OF content ON user_memory
  FOR EACH ROW EXECUTE FUNCTION update_fts_content();
```

### 8.7 Row Level Security (RLS)
```sql
-- Enable RLS on all user-data tables
ALTER TABLE conversations    ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages         ENABLE ROW LEVEL SECURITY;
ALTER TABLE tasks            ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks  ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_memory      ENABLE ROW LEVEL SECURITY;

-- Policy: service role bypasses RLS (used by FastAPI backend)
-- All backend DB access uses service role key — application enforces user_id in queries
-- RLS is a safety net, not the primary isolation mechanism
```

---

## 9. LangGraph: GenieState & Graph Wiring

> **Current reality (see §19):** only `build_chat_graph()` runs — `START → chat → END`,
> one node calling the LLM. The full supervisor wiring below is the target;
> `build_graph()` is still a stub. The compiled chat graph + `AsyncPostgresSaver`
> checkpointer are created once in the FastAPI lifespan and held via
> `set_runtime_graph()` / `get_runtime_graph()`.

### GenieState
```python
# app/agents/supervisor/state.py
from typing import Annotated, Any, Optional
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

class GenieState(TypedDict):
    messages:             Annotated[list, add_messages]   # append-only
    user_id:              str
    conversation_id:      str
    intent:               Optional[str]                   # extracted by supervisor
    active_agents:        list[str]                       # currently running
    intermediate_results: dict[str, Any]                  # keyed by agent name
    final_response:       Optional[str]
    token_usage:          dict[str, int]                  # {"total": N, "by_agent": {...}}
    user_memories:        list[dict]                      # injected at start
    should_interrupt:     bool                            # calendar write confirmation
    metadata:             dict[str, Any]
```

### RouteDecision (Pydantic — used by supervisor)
```python
class RouteDecision(BaseModel):
    agents: List[Literal["prompt_enhancer","web_search","rag","calendar","task_creator"]]
    rationale: str        # supervisor must explain why it chose these agents
    parallel: bool        # run agents concurrently when True
    requires_confirmation: bool  # set True for calendar writes
```

### Graph Wiring Pattern
```python
# app/agents/supervisor/graph.py
graph = StateGraph(GenieState)
graph.add_node("supervisor",       supervisor_node)
graph.add_node("prompt_enhancer",  prompt_enhancer_node)
graph.add_node("web_search",       web_search_node)
graph.add_node("rag",              rag_node)
graph.add_node("calendar",         calendar_node)
graph.add_node("task_creator",     task_creator_node)
graph.add_node("synthesiser",      synthesiser_node)

graph.set_entry_point("supervisor")
graph.add_conditional_edges("supervisor", route_to_agents)  # dynamic
# all agents → synthesiser
for agent in ["prompt_enhancer","web_search","rag","calendar","task_creator"]:
    graph.add_edge(agent, "synthesiser")
graph.add_conditional_edges("synthesiser", should_continue_or_end)

# Checkpointer: ALWAYS use session-mode connection
checkpointer = AsyncPostgresSaver.from_conn_string(settings.DATABASE_URL_SESSION)
compiled = graph.compile(
    checkpointer=checkpointer,
    interrupt_before=["calendar"]  # requires user confirmation
)
```

---

## 10. RAG Retriever Pattern

```python
# app/agents/rag/retriever.py
# ALWAYS use hybrid_search — never pure vector or pure FTS alone

async def hybrid_retrieve(
    query: str,
    user_id: str,
    match_count: int = 10
) -> list[dict]:
    embedding = await embed_text(query)  # text-embedding-3-small → 1536 dims
    
    result = await supabase.rpc(
        "hybrid_search_documents",
        {
            "query_text":      query,
            "query_embedding": embedding,
            "target_user_id":  user_id,
            "match_count":     match_count,
            "fts_weight":      1.0,      # tweak per use case
            "semantic_weight": 1.0,
            "rrf_k":           50
        }
    ).execute()
    
    return result.data   # [{id, content, metadata, document_id, score}]
```

---

## 11. Streaming Protocol (SSE)

### Event Types (strict — frontend parses by `type` field)

> Implemented today: `token`, `error`, `done` (see `core/streaming.py` +
> `lib/sse.ts`). The rest arrive with their features. The stream **always** ends
> with `done`, even after an `error` (§16).

```
data: {"type": "agent_start",   "agent": "web_search", "run_id": "..."}
data: {"type": "token",         "content": "Based on"}
data: {"type": "agent_end",     "agent": "web_search", "duration_ms": 1240}
data: {"type": "task_created",  "task": {"id": "...", "title": "...", "status": "todo"}}
data: {"type": "interrupt",     "reason": "calendar_write_confirmation", "details": {...}}
data: {"type": "error",         "message": "...", "code": "AGENT_TIMEOUT"}
data: {"type": "done",          "total_tokens": 1842, "run_id": "..."}
```

### Two-Step Chat Flow
1. `POST /api/v1/chat` — returns `{"run_id": "...", "conversation_id": "..."}`
2. `GET  /api/v1/chat/{conversation_id}/stream?run_id={run_id}` — SSE stream

### Chat Endpoint Logic (chat_service.py)
```
load_context(user_id) →           # Redis L1 + Supabase hybrid search L2
graph.astream_events(state, v2) → # yields events
convert to SSE protocol →
flush to client
persist message to Supabase →
publish SQS memory consolidation job
```

---

## 12. Agent Catalogue

| Agent | File | Runs When | Output to State |
|-------|------|-----------|-----------------|
| Prompt Enhancer | `agents/prompt_enhancer/` | First, always | `state.intent` + enhanced query |
| Web Search | `agents/web_search/` | Current events, facts | `state.intermediate_results["web_search"]` |
| RAG | `agents/rag/` | User asks about their docs | `state.intermediate_results["rag"]` |
| Calendar | `agents/calendar/` | Schedule/event queries | `state.intermediate_results["calendar"]`, `interrupt_before` writes |
| Task Creator | `agents/task_creator/` | Actionable tasks detected | `state.intermediate_results["task_creator"]` + SSE `task_created` event |

**Adding a new agent**:
1. Create `agents/new_agent/agent.py` with a `new_agent_node(state: GenieState)` function
2. Register in `supervisor/graph.py` (add_node + add_edge to synthesiser)
3. Add the literal to `RouteDecision.agents` Pydantic type
4. Update the supervisor system prompt in `supervisor/prompts.py` to describe the new agent
5. Write a unit test in `tests/agents/test_new_agent.py`

---

## 13. Memory Architecture

### L1 — Redis (TTL varies, ephemeral)
```
recent_messages:{user_id}     → list of last 10 messages (LPUSH/LTRIM, TTL 2h)
rate_limit:{user_id}:{min}    → request count (INCR/EXPIRE, TTL 1 min)
clerk:jwks                    → Clerk JWKS JSON (TTL 1h — see Section 7.7)
user_by_clerk:{clerk_id}      → internal user UUID (TTL 5 min — see Section 7.7)
```
Note: No JWT refresh tokens in Redis. Clerk manages sessions entirely.


### L2 — Supabase PostgreSQL (permanent)
- `messages` — full conversation history
- `user_memory` — extracted long-term facts (with embedding + fts_content)
- `document_chunks` — user's document RAG store

### Memory Load at Request Start
```python
# memory/manager.py
async def load_context(user_id: str, query: str) -> dict:
    recent   = await short_term.get_recent_messages(user_id)          # Redis
    memories = await long_term.hybrid_search_memories(query, user_id) # Supabase RPC
    return {"recent_messages": recent, "relevant_memories": memories}
```

### Memory Consolidation (after each conversation)
Triggered via SQS message. Worker:
1. Checks `processed_at IS NULL` (idempotency guard)
2. Calls LLM to extract structured facts from conversation
3. Embeds each fact (`text-embedding-3-small`)
4. Upserts to `user_memory` (trigger auto-populates `fts_content`)
5. Marks conversation `memory_consolidated = true`

---

## 14. API Endpoints Reference

```
# ── Webhooks (no auth — Svix signature verified internally) ─────────────────
POST   /api/v1/webhooks/clerk          → Clerk user lifecycle sync (user.created/updated/deleted)

# ── Users (Clerk JWT required) ───────────────────────────────────────────────
GET    /api/v1/users/me                → {id, email, full_name, avatar_url, token_budget}
                                         Use this to confirm user is synced after sign-up

# ── Chat (Clerk JWT required) ────────────────────────────────────────────────
POST   /api/v1/chat                    → {run_id, conversation_id}
GET    /api/v1/chat/{conv_id}/stream   → SSE stream  (query param: run_id)
POST   /api/v1/chat/{conv_id}/confirm  → resume after calendar write interrupt

# ── Conversations ─────────────────────────────────────────────────────────────
GET    /api/v1/conversations           → paginated list
GET    /api/v1/conversations/{id}      → conversation + messages
DELETE /api/v1/conversations/{id}      → 204

# ── Tasks ────────────────────────────────────────────────────────────────────
GET    /api/v1/tasks                   → list (filter: status, date)
PATCH  /api/v1/tasks/{id}              → update status/title
DELETE /api/v1/tasks/{id}              → 204

# ── Documents ────────────────────────────────────────────────────────────────
POST   /api/v1/documents               → upload (multipart) → S3 → SQS ingestion job → 202
GET    /api/v1/documents               → list user's documents
DELETE /api/v1/documents/{id}          → 204
```

**No `/auth/login`, `/auth/refresh`, `/auth/logout` routes.** Clerk handles all of this on the frontend. The backend only verifies JWTs — it never issues them.

---

## 15. Phase Roadmap

### PHASE 1 — Foundation (Weeks 1–3)
**Goal**: Single working end-to-end: user types → web search → streamed response.

**Backend tasks**:
- [x] FastAPI app factory with lifespan (startup: Redis ping, DB engine, checkpointer.setup())
- [x] `config.py` with pydantic-settings loading all env vars (including all CLERK_* vars)
- [x] `core/clerk.py`: `_get_jwks()` Redis-cached + `get_current_user()` — real RS256 verify; JWKS domain derived from `CLERK_PUBLISHABLE_KEY`; dev-user only when Clerk is unconfigured
- [x] `POST /webhooks/clerk`: Svix signature verification + user.created/updated/deleted handlers
- [x] `GET /users/me` — resolves the Clerk token → real internal user (auto-provisions, email from Clerk Backend API)
- [x] `UserRepository.create_from_clerk()` + `create_from_clerk_token()` + `update_from_clerk()` + `soft_delete_by_clerk_id()` + `touch_last_active()`
- [x] `request_id` middleware injected on all requests
- [x] Alembic: `users` (with `clerk_id` column, no `password_hash`), `conversations`, `messages` tables
- [x] `GenieState` TypedDict + `RouteDecision` Pydantic model
- [ ] Supervisor node with `with_structured_output(RouteDecision)` (no hardcoded routing)
- [ ] Web Search agent (Tavily) + Prompt Enhancer agent
- [ ] Synthesiser node
- [x] `AsyncPostgresSaver` checkpointer wired (session-mode URL) — live for the app lifetime, compiled with `build_chat_graph()`
- [x] `POST /chat` + `GET /chat/{id}/stream` SSE endpoints — _single-node `chat` graph, no supervisor yet_
- [x] SSE event protocol: `token`, `error`, `done` emitted — _`agent_start`/`agent_end` await the agent layer_
- [ ] Redis L1: `recent_messages`, `rate_limit` — _`memory/short_term.py` signatures only; `run:{id}` key is used by chat_
- [x] LangSmith tracing — `configure_tracing()` in the lifespan pushes `LANGSMITH_*` into `os.environ`; each chat turn's root run id is stored on the assistant message's `metadata.langsmith_run_id` and echoed in the SSE `done` event. Verified: traces land in the LangSmith project.
- [ ] Basic circuit breaker on LLM calls (`tenacity`, 3 retries, exponential backoff)

**Frontend tasks**:
- [x] Next.js **15** App Router scaffold + Tailwind v3 + shadcn/ui conventions (`components.json`, `ui/button`)
- [x] Install `@clerk/nextjs` (v7), `NEXT_PUBLIC_CLERK_*` via Clerk CLI, `<ClerkProvider>` in `<body>`
- [x] Route protection — _resource-based `await auth()` in `(app)/layout.tsx` (v7 style), not middleware matcher; `middleware.ts` runs bare `clerkMiddleware()`_
- [x] Sign-in page (`/sign-in/[[...sign-in]]`) and sign-up page using Clerk `<SignIn />` / `<SignUp />`
- [ ] After sign-up: call `GET /users/me` and wait for 200 before redirecting to `/chat` (webhook race condition guard)
- [x] Chat page: `ChatWindow`, `Message`, `StreamingDot` — _streams live tokens; input disabled mid-turn_
- [x] `useChat` hook: POST /chat → SSE connection → append tokens; rehydrates from `GET /conversations/{id}` on reload
- [x] `AgentActivity` component — _renders `chatStore.activeAgents`; needs real SSE events_
- [x] Zustand `chatStore`: messages, activeAgents, runId, conversationId
- [ ] Basic conversation sidebar (hardcoded single conversation for now)

**Database tasks**:
- [x] Run `setup_supabase.sql` (extensions, hybrid-search RPCs; indexes/RLS deferred to Phase 2)
- [x] Alembic migration: users, conversations, messages (`1c61bba11678`)
- [x] Verify LangGraph checkpointer tables created by `checkpointer.setup()`

**Phase 1 done when**: User can sign up via Clerk (Google or email), is auto-synced to the `users` table, send a message, see "web_search is thinking…" animate, receive a streamed response using live web data, and the conversation persists across page reload.

---

### PHASE 2 — RAG + Memory (Weeks 4–6)
**Goal**: Genie remembers the user and can search their documents.

**Backend tasks**:
- [ ] Alembic migration: `documents`, `document_chunks` (with `embedding vector(1536)`, `fts_content tsvector`)
- [ ] Run `setup_supabase.sql` sections: hybrid search functions, IVFFlat indexes, FTS triggers
- [ ] `document_service.py`: PDF/text → chunks (512 tokens, 50-token overlap) → embed → upsert
- [ ] Document ingestion SQS worker (`workers/document_ingestion.py`)
- [ ] `POST /documents` endpoint (upload → S3 → SQS job)
- [ ] RAG agent: calls `hybrid_search_documents` Supabase RPC, formats context
- [ ] Alembic migration: `user_memory` (with `embedding vector(1536)`, `fts_content tsvector`)
- [ ] FTS trigger for `user_memory` (add to `setup_supabase.sql`)
- [ ] `hybrid_search_memories` Supabase RPC function
- [ ] Memory manager: `load_context()` fetches Redis L1 + Supabase memories
- [ ] Memory consolidation SQS worker (LLM extraction → embed → upsert)
- [ ] Task Creator agent: `with_structured_output(ExtractedTask)` → persist to DB → emit SSE `task_created`
- [ ] Alembic migration: `tasks` table

**Frontend tasks**:
- [ ] Document upload UI in sidebar (drag-drop + file picker)
- [ ] Ingestion progress indicator (poll document status)
- [ ] Task Board: `/tasks` page, Kanban columns (todo / in-progress / done)
- [ ] Task cards created live from SSE `task_created` events (Zustand taskStore)
- [ ] `useTasks` hook with TanStack Query + optimistic updates

**Phase 2 done when**: User uploads a PDF, asks a question about it, gets an answer from their document (verify RAG agent was used via LangSmith trace). Long-term memories appear in context on next conversation. Tasks are created and visible on the board.

---

### PHASE 3 — Calendar + Async Workers (Weeks 7–8)
**Goal**: Google Calendar integration + fully async background processing.

**Backend tasks**:
- [ ] Google OAuth flow: `/auth/google`, `/auth/google/callback`
- [ ] Fernet-encrypt OAuth tokens before storing in `oauth_credentials` table
- [ ] Calendar agent: read events, create events with `interrupt_before`
- [ ] `POST /chat/{conv_id}/confirm` endpoint to resume interrupted graph
- [ ] SSE `interrupt` event type → frontend shows confirmation UI
- [ ] SQS consumer service (`workers/sqs_consumer.py`) as separate ECS service
- [ ] Full memory consolidation pipeline tested end-to-end
- [ ] Token budget enforcer in supervisor (check `state.token_usage` before routing)

**Frontend tasks**:
- [ ] Google OAuth "Connect Calendar" button in settings
- [ ] Calendar interrupt confirmation dialog (shown when SSE `interrupt` event received)
- [ ] Conversation list sidebar with titles and timestamps
- [ ] Settings page: connected services, document library

**Phase 3 done when**: User asks "schedule a meeting with John tomorrow at 3pm", Genie shows confirmation ("I'll create: Meeting with John, Aug 30, 3:00PM — Confirm?"), user confirms, event appears in Google Calendar.

---

### PHASE 4 — Infrastructure + Production Hardening (Weeks 9–10)
**Goal**: Deploy to AWS, production-ready.

**Infrastructure tasks**:
- [ ] Terraform: VPC, subnets, security groups
- [ ] Terraform: ALB (HTTPS, SSE idle timeout 300s)
- [ ] Terraform: ECS Fargate API service (autoscale 2–10, env from Secrets Manager)
- [ ] Terraform: ECS Fargate Worker service (autoscale 1–5)
- [ ] Terraform: ElastiCache Redis cluster
- [ ] Terraform: SQS queues + dead-letter queues
- [ ] Terraform: S3 (documents + CloudFront static assets)
- [ ] GitHub Actions CI/CD: test → build → ECR push → ECS rolling deploy
- [ ] CloudWatch alarms: LangGraph p95 latency, SQS queue depth, error rate
- [ ] AWS X-Ray integrated with FastAPI middleware
- [ ] Secrets Manager: all env vars rotated, 60-day DB password rotation disabled (Supabase manages DB password)
- [ ] Load test: 100 concurrent SSE streams (verify ALB idle timeout handles long streams)
- [ ] RLS policies hardened on all Supabase tables

**Phase 4 done when**: `git push main` deploys to production. CloudWatch shows healthy metrics. Load test passes.

---

### PHASE 5 — Intelligence + Expansion (Weeks 11+)
**Goal**: Make Genie smarter. Expand the agent catalogue.

- [ ] Memory importance scoring: LLM rates extracted facts 0–1, `importance` column in `user_memory`
- [ ] Memory decay: lower importance for older facts in hybrid search weighting
- [ ] Per-user token quotas: `token_budget` column in `users`, enforced in supervisor
- [ ] LangSmith evaluation datasets: build golden Q&A sets for each agent
- [ ] LangSmith CI evaluations: run on each deploy, gate on regression threshold
- [ ] Code Execution agent: sandboxed Python runner (AWS Lambda or Firecracker)
- [ ] Email agent: Gmail API read/compose (same OAuth pattern as Calendar)
- [ ] Notion agent: read/write pages (Notion API)
- [ ] Genie API: expose `/api/v1/run` for programmatic access (API key auth)
- [ ] Multi-modal: image upload → vision model → route to agents with image context
- [ ] CrewAI integration: wrap research-heavy tasks in a CrewAI crew called as a single LangGraph node

---

## 16. Testing Strategy

### Unit Tests (per agent, per service)
```
tests/
├── agents/
│   ├── test_supervisor.py      ← RouteDecision output for various queries
│   ├── test_web_search.py
│   ├── test_rag.py             ← Mock Supabase RPC, verify hybrid_search called
│   ├── test_task_creator.py    ← Verify ExtractedTask parsing
│   └── test_calendar.py        ← Verify interrupt_before triggers
├── services/
│   ├── test_chat_service.py
│   └── test_document_service.py  ← chunk + embed pipeline
├── memory/
│   ├── test_short_term.py
│   └── test_long_term.py       ← Mock Supabase RPC responses
└── api/
    ├── test_webhooks.py        ← Clerk webhook: valid/invalid Svix signature, all event types
    ├── test_users_me.py        ← get_current_user() with valid/expired/missing token
    ├── test_chat.py            ← POST /chat + SSE stream
    └── test_documents.py
```

### Key Test Assertions
- Supervisor NEVER routes to same agent twice in one run
- RAG retriever ALWAYS includes `user_id` filter
- Memory consolidation is idempotent (running twice produces same state)
- Token budget enforced: graph stops routing at 50k tokens
- SSE stream emits `done` event even when agent errors (error event first)
- Webhook with invalid Svix signature returns 400, never processes payload
- `get_current_user()` auto-creates user if webhook hasn't arrived (race condition test)
- All user-data repositories reject queries where `user_id` doesn't match token

---

## 17. Common Patterns & Conventions

### Python Conventions
```python
# Async everywhere — no sync DB calls in async code
# Pydantic v2 for all request/response models
# Type hints required on all function signatures
# Repository pattern: no raw SQL outside app/db/repositories/

# Log format (structured JSON via structlog)
logger.info("agent_completed", agent="web_search", duration_ms=1240, user_id=user_id)

# Never log: passwords, tokens, full message content (PII)
```

### TypeScript Conventions
```typescript
// App Router only — no getServerSideProps, no pages/
// Server Components by default — 'use client' only for interactive components
// TanStack Query for server state, Zustand for UI/streaming state
// All API calls go through lib/api.ts — never raw fetch in components
```

### Git Conventions
```
feat(rag): add hybrid search RPC integration
fix(supervisor): prevent duplicate agent routing
chore(infra): add ALB idle timeout terraform config

Branch: feat/phase-2-rag | fix/calendar-interrupt | chore/ci-ecr
```

---

## 18. Anti-Patterns — Never Do These

| ❌ Anti-Pattern | ✅ Correct Approach |
|----------------|---------------------|
| Building a custom login page with passwords | Use Clerk `<SignIn />` — it handles everything |
| Storing `password_hash` in the `users` table | `users` table has no password column |
| Minting JWTs in FastAPI | Never — only verify Clerk JWTs via JWKS |
| Fetching Clerk JWKS on every request | Cache JWKS in Redis for 1 hour (see `core/clerk.py`) |
| Storing `clerk_id` as FK on child tables | Store internal `users.id` UUID as FK always |
| Processing Clerk webhooks without verifying Svix signature | Always verify with `svix` library first |
| Redirecting to `/chat` immediately after sign-up | Call `GET /users/me` first; wait for 200 (webhook race guard) |
| `if "calendar" in query: route_to_calendar()` | LLM-based routing via `RouteDecision` |
| Raw `supabase.table().select()` in route handler | Call repository → call service |
| Synchronous document ingestion in request handler | Publish to SQS, return 202 Accepted |
| Storing raw OAuth tokens in DB | Fernet-encrypt before insert |
| `gpt-4o` (unpinned model string) | `gpt-4o-2024-08-06` always |
| Pure vector search for RAG | Hybrid search (RRF) always |
| Missing `user_id` filter in any DB query | All user-data queries filter by user_id |
| Single ECS service for API + worker | Two separate ECS services (scale independently) |
| Skipping memory consolidation "for now" | Build the schema for it in Phase 1 even if worker comes in Phase 3 |
| No `interrupt_before` for calendar writes | Always interrupt + confirm for any write to external systems |

---

## 19. Current Status

> **Keep this section current.** It is the source of truth for what is actually
> implemented. Update the ledger + phase table with every meaningful change, in
> the same commit as the code. Legend: ✅ working · 🟡 partial · ⬜ stub / not started.

_Last updated: 2026-08-29 — LangSmith tracing wired + run id captured._

| Phase | Status | Completion |
|-------|--------|-----------|
| Phase 0 — Scaffold | 🟢 Complete | 100% |
| Phase 1 — Foundation | 🟡 In Progress | ~50% |
| Phase 2 — RAG + Memory | 🔴 Not Started | 0% |
| Phase 3 — Calendar + Async | 🔴 Not Started | 0% |
| Phase 4 — Infrastructure | 🔴 Not Started | 0% |
| Phase 5 — Expansion | 🔴 Not Started | 0% |

### 19.1 Implementation ledger

**Backend** (`@clerk/…` n/a — FastAPI + uv; deps in `backend/requirements.txt`)
- ✅ App factory + lifespan (`main.py`): Redis ping, DB `SELECT 1`, `AsyncPostgresSaver.setup()` (non-fatal in dev)
- ✅ `config.py` (pydantic-settings, all §6 vars), `core/logging.py` (structlog JSON), `core/middleware.py` (`request_id` + timing), `core/exceptions.py`, `core/redis.py`, `core/streaming.py` (SSE frame helper)
- ✅ **LangSmith tracing** — `core/observability.py:configure_tracing()` (called first in the lifespan) copies `LANGSMITH_*` from Settings into `os.environ` so LangChain actually traces; each chat turn's root run id → `messages.metadata.langsmith_run_id` + the SSE `done` event.
- ✅ `GET /health`, `GET /health/ready` (Redis + DB checks)
- ✅ **Chat**: `POST /chat` (persist user msg + stash run in Redis) → `GET /chat/{id}/stream` SSE (`token`/`error`/`done`). Single-node LangGraph `chat` graph (`build_chat_graph`) → OpenAI `gpt-4o-2024-08-06`, compiled with a live `AsyncPostgresSaver` checkpointer held in the lifespan; `thread_id = conversation_id` gives multi-turn memory. Both messages persist to `messages`.
- ✅ `GET /conversations`, `GET /conversations/{id}` (conversation + messages); `conversation_repo` / `message_repo` real methods
- ✅ **Clerk auth** (`core/clerk.py`): JWKS fetched from the Frontend API host (derived from `CLERK_PUBLISHABLE_KEY`, or explicit `CLERK_DOMAIN`), Redis-cached (`clerk:jwks`); `RS256` verify; `sub` → internal user via Redis `user_by_clerk:{id}` → `UserRepository` → auto-provision (`create_from_clerk_token`, email/name enriched from the Clerk Backend API). `touch_last_active`. Dev-user fallback **only when no Clerk domain is configured**.
- ✅ `POST /webhooks/clerk` — Svix-verified; `user.created/updated/deleted` → `UserRepository`. Local: `clerk webhooks --forward-to …`. `user_repo` Clerk helpers all implemented.
- ✅ Dev user row seeded on startup **only when Clerk is unconfigured**
- ✅ Remaining §14 endpoints still return **501** (`/tasks`, `/documents`, `/chat/{id}/confirm`, `DELETE /conversations/{id}`)
- ✅ SQLAlchemy models `users` / `conversations` / `messages` + first Alembic migration (`1c61bba11678`, applied). Phase 2+ models are inert placeholder files.
- ✅ `GenieState` + `RouteDecision` (`agents/supervisor/state.py`) — real
- ⬜ Supervisor LLM routing, the 5 agents, synthesiser, full `build_graph()`, memory (`short_term`/`long_term`/`manager`), workers, LangSmith, rate limiting

**Frontend** (Next.js 15 · React 19 · Tailwind v3 · `@clerk/nextjs` v7 · npm)
- ✅ **Landing page** at `/` (`components/landing/*`) — voice-AI-concierge positioning, sticky blur nav w/ placeholder links, Framer-Motion hero "live call" animation (`CallOrb`: waveform → spoken request → agent chips → completed actions, loops; static under `prefers-reduced-motion`), logo marquee, how-it-works, features grid, "voice coming soon" band, CTA, 4-col footer. **`/` no longer redirects to `/chat`.**
- ✅ **Light/dark theme** — `next-themes` (`ThemeProvider` outermost in `layout.tsx`, `attribute="class"`, system default); `ThemeToggle` in the nav; global (also themes `/chat`, `/tasks`, Clerk pages). Dark palette = deep violet-black + violet glow.
- ✅ `(app)/` group with `Sidebar` (nav + live `BackendStatus` dot + Clerk buttons)
- ✅ `/chat` — real streaming chat: `useChat` hook (POST `/chat` → `fetch` the SSE stream → `parseSseStream` → `chatStore`), `ChatWindow` (max-w-3xl centred) renders tokens live and disables input while streaming; each `Message` shows a sender label — "GENIE" in the brand gradient w/ sparkle, the user's Clerk first name (`useUser()`). Conversation id in `localStorage`, rehydrated from `GET /conversations/{id}` on reload. `AgentActivity` present (no agent events emitted yet).
- ✅ `/tasks` — `TaskBoard` 3-column Kanban reading `taskStore`
- ✅ Zustand `chatStore` (messages, `conversationId`, `runId`) / `taskStore`; `lib/api.ts` (`postChat`, `getConversation`, `chatStreamUrl`, `getHealth`), `lib/sse.ts` parser matching `core/streaming.py`
- ✅ Clerk: `ClerkProvider` in `<body>` themed via `lib/clerk-appearance.ts`; `middleware.ts` = bare `clerkMiddleware()` + `/__clerk/:path*` matcher; `(app)/layout.tsx` gate via `await auth()`; sign-in/up pages; `clerk doctor` passes
- ⬜ `useTasks` (enabled), conversation sidebar list, document upload UI

**Auth end-to-end**
- ✅ Frontend: real Clerk (dev instance `ins_3Ia08…`, app `app_3Ia08IpcDiBIMwI1FykjqEgLCMm`), keys in `frontend/.env.local`; `useChat` / `lib/api.ts` attach `Authorization: Bearer <getToken()>` on `POST /chat`, the stream fetch, and `GET /conversations/{id}`.
- ✅ Backend verifies the Clerk JWT and owns each conversation with the **real** internal user id. Needs `CLERK_PUBLISHABLE_KEY` (JWKS domain) + `CLERK_SECRET_KEY` (profile/webhook) in `backend/.env`; `CLERK_WEBHOOK_SECRET` for the webhook. Missing/expired token → `401`. With none of these set, the dev-user fallback keeps local work frictionless.

**Infra / local dev**
- ⚠️ The frontend talks to the API at **`http://127.0.0.1:8000`**, not `localhost` — browsers often resolve `localhost` to IPv6 (`::1`) first and a default uvicorn is IPv4-only, which makes the health check spuriously report "offline". `NEXT_PUBLIC_API_URL` + the `lib/api.ts` fallback use `127.0.0.1`; `CORS_ALLOW_ORIGINS` lists both `:3000` hosts.
- ✅ `docker-compose.yml` → Redis (`:6379`) + LocalStack (`:4566`). Postgres/pgvector comes from the **Supabase CLI** stack (`supabase start`, `:54322`); `DATABASE_URL_*` point at the default `postgres` db, Genie's tables live in the **`genie` schema** (visible in Studio).
- ✅ `scripts/setup_supabase.sql` — `CREATE SCHEMA genie` + hybrid-search RPCs (in `genie`, `SET search_path`); indexes/FTS triggers/RLS self-skip until Phase 2 tables exist.
- ⬜ `infrastructure/terraform` (Phase 4), SQS/S3 wiring, CI/CD.

### 19.2 Next up (Phase 1)

Grow `build_chat_graph()` into the supervisor: `with_structured_output(RouteDecision)`
routing → `prompt_enhancer` + `web_search` agents → synthesiser (emit
`agent_start`/`agent_end` SSE) → Redis `recent_messages` / `rate_limit` +
token-budget check → conversation sidebar list. Frontend `GET /users/me` gate
after sign-up (webhook race guard, §7.8).

> **Interim note (CLAUDE.md §9/§11):** the running graph is a single `chat` node,
> not the supervisor. SSE currently emits only `token` / `error` / `done`.
> `chat_service` calls the model directly through the graph — no agents, tools,
> RAG or memory-consolidation yet.

---

## 20. Quick Reference: Key Files Per Feature

| Feature | Primary Files |
|---------|--------------|
| Auth / user verification | `core/clerk.py` (JWT verify) + `api/v1/endpoints/webhooks.py` (sync) |
| User DB record | `db/models/user.py` + `db/repositories/user_repo.py` |
| Clerk JWKS cache tuning | `JWKS_CACHE_TTL_SECONDS` env var (default 3600) |
| Add a new agent | `agents/{name}/agent.py` + `supervisor/graph.py` + `supervisor/prompts.py` |
| Change routing logic | `supervisor/nodes.py` → `RouteDecision` prompt in `supervisor/prompts.py` |
| Modify hybrid search weights | `agents/rag/retriever.py` → `fts_weight`, `semantic_weight` params |
| Add a new API endpoint | `api/v1/endpoints/{resource}.py` + register in `api/v1/router.py` |
| Add DB table | New SQLAlchemy model in `db/models/` + Alembic migration + repository |
| Change SSE event schema | `core/streaming.py` + `frontend/src/lib/sse.ts` (must stay in sync) |
| Update memory consolidation | `workers/memory_consolidation.py` + `memory/long_term.py` |
| Tune token budget | `MAX_TOKENS_PER_RUN` env var + check in `supervisor/nodes.py` |
