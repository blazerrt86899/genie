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
| Tool servers | **FastMCP** (`fastmcp>=3`) | Centralized MCP layer — `app/mcp/*` (§22) |
| Chat model | **Per-conversation, user-picked** — `MODEL_CATALOG` in `agents/models.py` (OpenAI · Anthropic · Groq) | The composer's model picker sets `conversations.model` (a catalog id, e.g. `claude-sonnet`); `resolve_model_spec(None)` falls back to `settings.LLM_PROVIDER` + `settings.chat_model_name`. One unified `_build(provider, model, …)` — `ChatOpenAI` / `ChatAnthropic` / `ChatGroq` — used by the supervisor plan, the streamed answer, and the `web_search` / `task_creator` agents. All SDKs share exception names so retry/token helpers stay provider-agnostic. |
| Utility model | `settings.LLM_PROVIDER` + `settings.utility_model_name` (never user-picked) | The cheap internal calls: `prompt_enhancer` / `greeting` / title / `validator`. `groq` default = `qwen/qwen3.8-27b`. |
| Embeddings | OpenAI `text-embedding-3-small` | 1536 dims — **always OpenAI**, regardless of `LLM_PROVIDER` |
| Task Queue | AWS SQS (LocalStack local) | Standard queue, idempotent consumers. `core/aws.py` — `boto3`, endpoint-override for LocalStack |
| Background Worker | `workers/ingestion_worker.py` | KB ingestion. Dev: in-process from the lifespan (`RUN_INGESTION_WORKER`). Prod: separate ECS service (`python -m`) |
| Doc parsing | `pdfminer.six` (PDF) · `unstructured` (md/txt + `chunk_by_title`) · `pypdf` (attachments) | "fast" — no OCR / layout ML model |
| Auth | **Clerk** | Hosted auth, webhook sync to DB, JWKS-verified JWT in FastAPI |
| Observability | LangSmith + AWS X-Ray | Trace every graph run |
| LLM SDKs | `langchain-openai` · `langchain-anthropic` · `langchain-groq` | All via `agents/models.py` — no direct imports elsewhere |
| Circuit Breaker | `tenacity` | Exponential backoff, 4 attempts (`wait_exponential(2..30s)` — rides out a Groq free-tier 429) |
| Validation | Pydantic v2 | All request/response models |

### Database
| Component | Choice | Notes |
|-----------|--------|-------|
| Primary DB | **Supabase Cloud PostgreSQL** | Managed, pgvector + tsvector enabled |
| ORM | SQLAlchemy 2.0 (async) | For complex queries + LangGraph checkpointer |
| Supabase Client | `supabase-py` | For auth helpers, storage, realtime |
| Migrations | Alembic | Only for app tables — NOT checkpointer tables |
| Vector Search | pgvector (`vector(1536)`) | HNSW index (small tables → ivfflat has near-zero recall), cosine ops |
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
| Markdown | `react-markdown` v9 + `remark-gfm` + `rehype-highlight` (`highlight.js` common set) | Renders Genie replies (`components/chat/Markdown.tsx` + `CodeBlock.tsx`). GFM tables, fenced code with language label + copy + syntax highlighting themed from CSS vars (`globals.css` `.hljs-*`). A ```` ```document ```` fence → `DocumentCard.tsx` (business-comms draft: kind header, Subject row, Copy). NOT `rehype-raw` — no raw-HTML passthrough (zero XSS surface). User messages stay plain text. |

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

8. **Observability from day one** — Every module logs its every step through `structlog` (see §21 — event names, levels, `preview()` for user content, automatic secret redaction). Every agent node emits a LangSmith trace. Every API request gets a `request_id` injected by middleware. Every SQS job gets a `job_id`. Logs are structured JSON in prod, headed for Datadog.

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
│       │       ├── chat.py            ← /chat (POST), /chat/{id}/stream (GET SSE), /chat/{id}/regenerate (POST — retry/edit/regenerate)
│       │       ├── conversations.py   ← /conversations list · GET · PATCH · DELETE · {id}/share (GET/POST/DELETE)
│       │       ├── messages.py        ← POST /messages/{id}/feedback — 👍/👎 (metadata + best-effort LangSmith)
│       │       ├── public.py          ← GET /public/shared/{token} — unauthenticated read-only shared chat
│       │       ├── models.py          ← GET /models (the composer's model-picker catalog)
│       │       ├── attachments.py     ← POST/DELETE /attachments (composer "+" file uploads)
│       │       ├── tasks.py           ← /tasks CRUD
│       │       └── documents.py       ← /documents upload + list
│       │
│       ├── agents/
│       │   ├── base.py                ← AgentResult dataclass
│       │   ├── models.py              ← MODEL_CATALOG + resolve_model_spec · _build(openai|anthropic|groq) · get_chat_model(model_id) / get_utility_model / ainvoke (retry) / tokens_of
│       │   ├── registry.py            ← AGENT_REGISTRY, AgentSpec, agent_menu()
│       │   ├── supervisor/
│       │   │   ├── graph.py           ← build_graph(): prompt_enhancer→retriever→supervisor→executor→synthesiser→validator
│       │   │   ├── state.py           ← GenieState + TaskRecord + SupervisorPlan + EnhancedPrompt + Validation
│       │   │   ├── nodes.py           ← supervisor / executor / synthesiser / validator nodes
│       │   │   └── prompts.py         ← supervisor (registry-driven) / synthesiser / validator prompts
│       │   │
│       │   ├── greeting/              ← registered agent: time-of-day greeting
│       │   │   ├── agent.py           ← run_greeting(state, task) → AgentResult
│       │   │   └── prompts.py
│       │   │
│       │   ├── prompt_enhancer/       ← graph node (always first, not a registry agent)
│       │   │   ├── agent.py           ← prompt_enhancer_node → {intent, enhanced_query}
│       │   │   └── prompts.py
│       │   │
│       │   ├── web_search/            ← registered agent: Tavily
│       │   │   ├── agent.py           ← run_web_search(state, task) → AgentResult
│       │   │   ├── prompts.py
│       │   │   └── tools.py           ← tavily_search(), format_results(), extract_sources()
│       │   │
│       │   ├── rag/                   ← ⬜ the future RAG *agent* (multi-store routing) — NOT the project KB pipeline (§10)
│       │   │   ├── agent.py           ← stub
│       │   │   ├── retriever.py       ← stub
│       │   │   └── embedder.py        ← ✅ embed_batch/embed_text → OpenAI text-embedding-3-small
│       │   │
│       │   ├── calendar/
│       │   │   ├── agent.py           ← interrupt_before writes
│       │   │   └── tools.py           ← Google Calendar API wrappers
│       │   │
│       │   ├── task_creator/         ← registered agent: task board via the tasks MCP
│       │   │   ├── agent.py           ← run_task_creator(state, task) → AgentResult
│       │   │   ├── prompts.py
│       │   │   └── schemas.py         ← TaskOp / TaskOps structured output
│       │   │
│       │   └── events.py              ← emit(name, data) — agent custom events → SSE (§11)
│       │
│       ├── mcp/                       ← MCP layer (§22) — FastMCP tool servers
│       │   ├── tasks_server.py        ← FastMCP("genie-tasks"): task CRUD tools
│       │   └── client.py              ← call_tasks_tool() — in-process in-memory client
│       │
│       ├── schemas/
│       │   └── rag.py                 ← RagSettings (projects.rag_settings) — search strategy + params (§10)
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
│       │       ├── conversation_repo.py  ← + project_repo.py
│       │       ├── message_repo.py
│       │       ├── task_repo.py
│       │       ├── attachment_repo.py
│       │       ├── document_repo.py         ← ✅ KB documents (status/phase/stats)
│       │       ├── document_chunk_repo.py   ← ✅ bulk_insert chunks (embedding + fts)
│       │       └── memory_repo.py
│       │
│       ├── services/
│       │   ├── chat_service.py        ← Orchestrates memory load + graph run + SSE
│       │   ├── task_service.py        ← task board logic (REST + MCP + tests call this)
│       │   ├── attachment_service.py  ← parse pdf/txt/md → text; persist; link to a message
│       │   ├── title_service.py       ← cheap-LLM conversation titles
│       │   ├── memory_service.py      ← Memory consolidation logic
│       │   ├── document_service.py    ← KB: validate → S3 put → row → SQS enqueue; list/get/chunks/delete
│       │   └── rag/
│       │       ├── partition_service.py  ← pdf (pdfminer) / md·txt (unstructured) → typed Elements
│       │       ├── chunk_service.py      ← chunk_by_title → Chunk[] (size/overlap from RagSettings)
│       │       └── retrieval_service.py  ← retrieve(project, query, RagSettings) — vector / hybrid RPC / multi-query + RRF
│       │
│       ├── workers/
│       │   ├── sqs_consumer.py        ← (stub)
│       │   ├── memory_consolidation.py
│       │   └── ingestion_worker.py    ← ✅ SQS poll → ingest_document (partition→chunk→vectorize→store) + Redis progress
│       │
│       └── core/
│           ├── clerk.py               ← JWKS fetch+cache, RS256 verify, get_current_user()
│           ├── clerk_api.py           ← thin Clerk Backend API client (profile enrichment)
│           ├── aws.py                 ← boto3 s3()/sqs() singletons (LocalStack ↔ real AWS) + ensure_infra()
│           ├── redis.py               ← async Redis client singleton
│           ├── streaming.py           ← SSE frame helpers (§11)
│           ├── observability.py       ← configure_tracing() — LangSmith → os.environ
│           ├── logging.py             ← structlog config + redact_processor + preview()/mask() (§21)
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
│       │   ├── sign-up/[[...sign-up]]/page.tsx   ← Clerk hosted <SignUp forceRedirectUrl="/welcome">
│       │   ├── welcome/page.tsx         ← post-sign-up: poll GET /users/me → /chat (§7.8)
│       │   ├── share/[token]/           ← public read-only shared chat (page.tsx + not-found.tsx) — outside (app), no auth
│       │   └── (app)/
│       │       ├── layout.tsx         ← auth() gate (redirect to /sign-in) + Sidebar
│       │       ├── chat/page.tsx      ← new chat  ·  chat/[id]/page.tsx ← a conversation
│       │       ├── projects/page.tsx  ← project grid  ·  projects/[id]/page.tsx ← a project
│       │       └── tasks/page.tsx     ← Task board
│       │
│       ├── components/
│       │   ├── Sidebar.tsx            ← New chat · Projects · Tasks · Pinned + Chats lists (read/unread bullet, per-row ConversationMenu) · account · drag-to-resize (blur scrim while dragging)
│       │   ├── BackendStatus.tsx      ← live GET /health dot (TanStack Query)
│       │   ├── projects/              ← ProjectsIndex, ProjectView, NewProjectDialog
│       │   │   └── knowledge-base/    ← KnowledgeBasePanel · DocumentUpload · DocumentList · PipelineModal · ChunkViewer · RagSettingsForm
│       │   ├── landing/               ← SiteHeader, Hero, CallOrb (hero animation),
│       │   │                              ThemeToggle, LogoMarquee, HowItWorks, Features,
│       │   │                              VoiceComingSoon, CtaBand, Footer, Container, Wordmark
│       │   ├── chat/
│       │   │   ├── ChatView.tsx       ← ChatHeader + PlanStrip + message list + composer
│       │   │   ├── ChatHeader.tsx     ← top bar: pin glyph + title + ⋯ menu + Share button; scroll-shadow when scrolled
│       │   │   ├── ConversationMenu.tsx← shared ⋯ dropdown: Pin · Mark read/unread · Rename · Add to project · Delete
│       │   │   ├── ShareChatModal.tsx ← Keep private ↔ Create public link + copy — POST/DELETE /conversations/{id}/share
│       │   │   ├── Message.tsx        ← user = subtle box (plain text) + inline edit · Genie = borderless rich Markdown; + MessageActions row
│       │   │   ├── MessageActions.tsx ← per-message row: Copy · 👍/👎 · Regenerate (assistant) / Retry · Edit (user) · date
│       │   │   ├── Markdown.tsx       ← react-markdown + remark-gfm + rehype-highlight; token-styled headings/tables/lists/quotes
│       │   │   ├── CodeBlock.tsx      ← fenced-code chrome: language label + Copy button over the hljs-tokenised <pre>
│       │   │   ├── DocumentCard.tsx   ← ```document fence → boxed draft (email/letter/application/memo…): kind header · Subject row · Copy
│       │   │   ├── SourceCards.tsx    ← the `sources` SSE event / metadata → link cards (http(s)-only href on the public page)
│       │   │   ├── AgentActivity.tsx  ← tail pill for an unclaimed active agent
│       │   │   ├── PlanStrip.tsx      ← the `plan` SSE event → numbered steps + status
│       │   │   ├── ModelPicker.tsx    ← composer model dropdown (useModels + chatStore.model)
│       │   │   ├── PlusMenu.tsx       ← composer "+" — Add files · Add to project
│       │   │   ├── AttachmentChips.tsx← staged uploads shown in the composer
│       │   │   └── StreamingDot.tsx   ← Animated typing indicator
│       │   ├── tasks/
│       │   │   ├── TaskBoard.tsx      ← 3 cols + HTML5 drag + "Archive done" + "Archived (N)"
│       │   │   ├── TaskCard.tsx       ← draggable; opens the modal
│       │   │   └── TaskModal.tsx      ← detail: status · linked chat · editable description · delete
│       │   └── ui/                    ← shadcn/ui primitives (button, modal)
│       │
│       ├── hooks/
│       │   ├── useChat.ts             ← route-driven: load /chat/[id], POST + SSE, router.replace on new
│       │   ├── useConversations.ts    ← TanStack Query list + patch (title/project/pinned/unread) + delete mutations
│       │   ├── useModels.ts           ← GET /models catalog (staleTime ∞) for the picker
│       │   ├── useAttachments.ts      ← upload/delete → chatStore.pendingAttachments
│       │   ├── useProjects.ts         ← projects list/detail/CRUD (TanStack Query)
│       │   ├── useDocuments.ts        ← KB list (polls while ingesting) + upload/delete + useDocumentPipeline (SSE)
│       │   ├── useShareConversation.ts← share state query + enable/disable mutations (["share", id])
│       │   ├── useScrollShadow.ts     ← {atTop, atBottom} for a scroll container → sticky-header/footer shadow
│       │   └── useTasks.ts            ← tasks list + patch/archive-done/delete (TanStack Query)
│       │
│       ├── providers/
│       │   ├── query-provider.tsx     ← TanStack QueryClientProvider
│       │   └── theme-provider.tsx     ← next-themes ThemeProvider
│       │
│       ├── store/
│       │   └── chatStore.ts           ← Zustand: messages, active agents, run_id
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
FRONTEND_BASE_URL=http://localhost:3000   # absolute base for public share URLs ({base}/share/{token}); no trailing slash

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
# LLM_PROVIDER = the *fallback* chat model + the (fixed) utility model. The chat
# model is otherwise picked per conversation from MODEL_CATALOG — any provider
# below whose key is set shows up in the composer's picker.
LLM_PROVIDER=openai          # openai | groq  — groq = OpenAI-credit-free testing
OPENAI_API_KEY=
ANTHROPIC_API_KEY=           # powers the Claude models in the picker
ANTHROPIC_WORKSPACE_ID=      # only for identity-linked keys ("anthropic-workspace-id is required")
OPENAI_CHAT_MODEL=gpt-4o-2024-08-06   # ALWAYS pin the model version — never use "gpt-4o"
OPENAI_TITLE_MODEL=gpt-4o-mini        # cheap model for auto conversation titles
OPENAI_EMBEDDING_MODEL=text-embedding-3-small   # embeddings ALWAYS stay on OpenAI

# Only used when LLM_PROVIDER=groq. Free tier ≈ 8k TPM — a busy multi-agent turn
# can brush it; models.ainvoke() retries the 429 (tenacity, up to ~30s).
GROQ_API_KEY=
GROQ_CHAT_MODEL=openai/gpt-oss-120b       # supervisor / synthesiser / agents
GROQ_UTILITY_MODEL=qwen/qwen3.8-27b       # enhancer / greeting / titles / validator

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

# ─── MCP (§22) — only used when a server runs standalone; agents use in-process ──
TASKS_MCP_HOST=127.0.0.1
TASKS_MCP_PORT=8765

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
      {/* → /welcome polls GET /users/me until the webhook has created the row (§7.8) */}
      <SignUp forceRedirectUrl="/welcome" />
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
Alembic manages schema for: `users`, `conversations`, `messages`, `tasks`, `attachments`, `documents`, `document_chunks`, `user_memory`, `agent_runs`, `oauth_credentials`.

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
CREATE INDEX ON document_chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
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

> **Current reality (see §19):** the real graph runs —
> `START → prompt_enhancer → retriever → supervisor → executor → synthesiser → validator → {supervisor | END}`.
> Three agents are registered (`greeting`, `web_search`, `task_creator`);
> `prompt_enhancer` and `retriever` are **pipeline nodes**, not registry agents
> (`retriever` = the project Knowledge Base, §10 — runs only when the chat's
> project has a ready KB and the enhancer set `needs_documents`); the `rag`/`calendar`
> dirs are still stubs. The compiled graph + `AsyncPostgresSaver` checkpointer are
> created once in the FastAPI lifespan and held via `set_runtime_graph()` / `get_runtime_graph()`.

### GenieState (`app/agents/supervisor/state.py`)
```python
class TaskRecord(TypedDict):          # one row of the supervisor's task ledger
    id: str                           # "t1", "t2", …
    description: str
    agent: str                        # registry key
    status: Literal["pending","in_progress","done","failed"]
    depends_on: list[str]             # ids that must be "done" first
    result: str | None                # the agent's summary once done
    error: str | None

class GenieState(TypedDict):
    messages:             Annotated[list, add_messages]   # append-only
    user_id:              str
    conversation_id:      str
    project_instructions: str | None                     # prepended to the system prompt (Projects)
    client_hour:          int | None                     # user's local hour 0-23 (time-aware agents)
    model:                str | None                     # picked chat-model id (MODEL_CATALOG); None → server default
    attachments:          list[dict]                     # [{filename,kind,text}] — files sent with THIS turn only
    rag_settings:         dict | None                    # the project's RagSettings (§10); None outside a KB project
    has_kb:               bool                           # the project has ≥1 ready document
    needs_documents:      bool                           # the enhancer's gate for running retrieval this turn
    retrieved_chunks:     list[dict]                     # [{content, similarity, heading, filename}] from the KB
    intent:               str | None                     # short label from the prompt_enhancer
    enhanced_query:       str | None                     # latest message rewritten self-contained (prompt_enhancer)
    plan:                 list[TaskRecord]               # the task ledger — supervisor writes, executor updates
    supervisor_turns:     int                            # (re)plan count — capped by SUPERVISOR_MAX_TURNS
    active_agents:        list[str]
    intermediate_results: dict[str, Any]                  # keyed by agent name: {summary, detail, sources}
    final_response:       str | None
    validation:           dict | None                    # {"approved": bool, "issues": [...]}
    token_usage:          dict[str, int]
    user_memories:        list[dict]
    should_interrupt:     bool
    metadata:             dict[str, Any]
```

### SupervisorPlan (Pydantic — the supervisor's structured output)
```python
class PlanStep(BaseModel):
    description: str                  # what this step accomplishes / the search query
    agent: str                        # must be a registered agent (KNOWN_AGENTS) — LLM's choice
    depends_on: list[int] = []        # 1-based positions of earlier steps it needs

class SupervisorPlan(BaseModel):
    steps: list[PlanStep] = []        # empty ⇒ no agent needed, synthesiser answers directly
    rationale: str
```
`nodes._plan_to_ledger()` validates: drops unknown agents, dedupes (no agent
twice per plan — §16), remaps `depends_on` → task ids.

### Agent registry (`app/agents/registry.py`)
`AGENT_REGISTRY: dict[str, AgentSpec]` — each `AgentSpec(name, description,
runner)` where `runner(state, task) -> AgentResult(summary, detail, sources)`
(`app/agents/base.py`). The supervisor prompt is generated from `agent_menu()`.
Add an agent = add an `AgentSpec` here (+ its module) — no graph node needed, the
`executor` dispatches through the registry.

### Graph wiring (`app/agents/supervisor/graph.py`)
```python
graph = StateGraph(GenieState)
graph.add_node("prompt_enhancer", prompt_enhancer_node)  # rewrite self-contained + intent + needs_documents
graph.add_node("retriever",   retriever_node)    # project Knowledge Base (§10) — runs iff has_kb & needs_documents
graph.add_node("supervisor",  supervisor_node)   # LLM plan → task ledger
graph.add_node("executor",    executor_node)     # walk ledger, run agents in dep order, update statuses
graph.add_node("synthesiser", synthesiser_node)  # compose the one user-facing reply (streams)
graph.add_node("validator",   validator_node)    # non-empty + LLM grounding check when agents ran

graph.add_edge(START, "prompt_enhancer")
graph.add_edge("prompt_enhancer", "retriever")
graph.add_edge("retriever", "supervisor")
graph.add_edge("supervisor", "executor")
graph.add_edge("executor", "synthesiser")
graph.add_edge("synthesiser", "validator")
graph.add_conditional_edges("validator", route_after_validator,
                            {"supervisor": "supervisor", END: END})  # capped re-plan loop
```
Compiled in the lifespan with the session-mode `AsyncPostgresSaver`. No
`interrupt_before` yet (calendar agent not built). Every non-streaming LLM call
goes through `agents/models.py:ainvoke()` (tenacity — 4 attempts, exponential
backoff on transient OpenAI / Anthropic / Groq errors); `prompt_enhancer` / `supervisor` /
`synthesiser` / `validator` accumulate `token_usage` so the supervisor's
`MAX_TOKENS_PER_RUN` guard bites on a re-plan.

**Chat model per turn** — `chat_service._generate` seeds `GenieState['model']`
from `conversations.model` (the picker). The four chat-model call sites —
`supervisor_node`, `synthesiser_node` (×2), `run_web_search`, `run_task_creator` —
pass `model_id=state.get("model")` into `get_chat_model()`, which resolves it
against `MODEL_CATALOG` (unknown / keyless id → the server default, logged). The
`get_utility_model()` call sites are unaffected.

**Attachments per turn** — the composer "+" menu uploads a `pdf` / `txt` / `md`
file (`POST /attachments` → `attachment_service.parse_upload` → the `attachments`
table). `POST /chat` carries `attachment_ids`; `create_turn` links them to the
user message + writes `message_metadata.attachments`; `_generate` loads the text
into `GenieState['attachments']` (this turn only — **one-shot**). In `nodes.py`:
`_attachment_note()` (filenames + rough size) goes to the prompt_enhancer +
supervisor so they know a file is in play and skip a web search; `_augment_system`
appends the **full** budgeted text (`_format_attachments`, `_ATTACHMENT_CHAR_BUDGET
= 24_000` ≈ 6k tokens, per-file `…[truncated N chars]`) to the synthesiser's
system prompt only.

**Executor** runs agents **sequentially** in dependency order — a later agent
sees earlier `intermediate_results` (keyed by **task id**, not agent name, so an
agent can appear in several steps for distinct sub-tasks; `_plan_to_ledger` only
drops exact `(agent, description)` repeats and caps the plan at 6). It
`adispatch_custom_event`s `agent_start` / `agent_end` / `plan`, and — for an
`AgentResult(stream=True)` (e.g. the greeting) — a **`segment`** event carrying
that step's output, emitted the moment the step finishes so the user sees it
before later steps run.

**Synthesiser** composes the reply to the *request* from the non-streamed
findings only — it NEVER repeats a streamed segment (told "a greeting was already
sent separately — don't greet again"). Lone greeting / all-streamed ⇒ no LLM
call. Empty plan ⇒ it answers the user directly.

**Regenerate / retry / edit** (`chat_service.regenerate_turn`, `POST /chat/{id}/regenerate`)
truncate the conversation at a message and re-run: pick the anchor user message
(the one before an assistant target, or the target itself for a user message —
optionally with `edit` replacing its text), `messages.delete_after(anchor)`,
`checkpointer.adelete_thread(cid)`, stash a `mode="regenerate"` run. `_generate`
then seeds `state["messages"]` by replaying the surviving `messages` rows
(Human/AI) instead of `[HumanMessage(new)]` — the just-reset thread starts empty
so there's no double-merge.

**The synthesiser is also Genie's response drafter.** `RESPONSE_FORMAT_GUIDE`
(`agents/supervisor/prompts.py`) is appended to both user-facing prompts
(`SYNTHESISER_SYSTEM_PROMPT`, `CHAT_SYSTEM_PROMPT`) — it tells the model to pick
the lightest structure that fits and to use GFM: styled headings only for long
multi-part answers, pipe tables for comparative/key-value data, **fenced code
blocks with an explicit language tag** for every code / query / config / command,
inline code for identifiers, blockquotes for caveats, `[1]` inline citations (no
"Sources" list). No separate formatting pass — one streamed call. The frontend
(`components/chat/Markdown.tsx`) renders it richly.

`DOCUMENT_BLOCK_GUIDE` (same file, also on both prompts) tells the drafter: when
the user asks it to WRITE a business communication (email / letter / cover
letter / application / memo / proposal / agenda / message / notice), emit the
finished document inside a ```` ```document ```` fence — `key: value` metadata
(`kind:` always, `subject:` / `to:` for mail), a `---`, then the body. The
frontend renders that as a `DocumentCard`.

`chat_service` forwards the graph's `message_break` / `message_agents` / `segment`
custom events, splitting the turn into one `messages` row per assistant message —
so "Hi, weather in Mussoorie?" comes back as two messages (greeting, then
forecast), each captioned in the UI with the agent that produced it
(`AgentSpec.stream` marks an agent whose output is its own message).

---

## 10. Project Knowledge Base (project-scoped RAG)

> Each **project** has a Knowledge Base. This is a **project pipeline**, not a
> registry agent — `agents/rag/` stays reserved for a future RAG *agent* (intelligent
> multi-store routing). Retrieval is wired into the chat flow in **commit 2**.

### Ingestion (commit 1 — DONE)
```
POST /api/v1/documents (multipart)          # document_service.create_and_enqueue
  → validate pdf/md/txt ≤ 25 MB
  → aws.s3().put_object  (LocalStack local; S3 on prod)
  → documents row (status=queued, phase=upload)
  → aws.sqs().send_message {"job":"ingest_document","document_id":…}

ingestion_worker.poll_loop()                # dev: in-process; prod: separate ECS
  → ingest_document(id)  [idempotent: skip when status=ready / processed_at set]
      partition   partition_service.partition(kind, s3 bytes) → typed Elements + stats
      chunk       chunk_service.chunk(elements, chunk_size, chunk_overlap)  (unstructured chunk_by_title)
      vectorize   embedder.embed_batch(chunk texts) → OpenAI text-embedding-3-small (1536-d)
      store       document_chunk_repo.bulk_insert  (embedding + trigger-filled fts_content)
      → documents.status=ready, processed_at=now(); each phase → documents.phase + redis PUBLISH doc_pipeline:{id}
```
`GET /api/v1/documents/{id}/stream` (SSE) relays the Redis channel so the
Knowledge-Base pipeline modal updates live.

### Retrieval (commit 2 — DONE)
`services/rag/retrieval_service.retrieve(db, project_id, user_id, query, RagSettings)`
— strategy from `projects.rag_settings` (`schemas/rag.py:RagSettings`):
`vector` (pgvector cosine top-k, `similarity_threshold` floor) · `hybrid` (the
`genie.hybrid_search_project_chunks` RPC — RRF over semantic + FTS) ·
`multi_query_*` (utility-model writes `num_queries` paraphrases → base strategy
per query → RRF-fuse → top `final_context_size`).

Wired as a **`retriever` graph node** (`nodes.retriever_node`) between
`prompt_enhancer` and `supervisor`. Runs only when `state.has_kb` (the project has
a ready document) **and** `state.needs_documents` (the enhancer's gate — false for
greetings / small talk). Emits `agent_start`/`agent_end` for `kb_search` and
**seeds a completed `knowledge_base` ledger step** so the plan strip shows it.
`supervisor_node` merges that step and `_kb_note` tells the supervisor: KB was
already searched → return an **empty** plan (no `web_search` for anything a
document could hold) unless the request also needs live external facts.
`nodes._format_kb` (chunks, 12k-char budget) → synthesiser via `_augment_system`;
the answer is captioned `kb_search`. `chat_service._generate` loads `rag_settings`
+ `has_kb`. **Index: HNSW** — ivfflat's recall collapses on a small per-project
table (a few chunks in 100 lists → a query probes ~1 → finds nothing).
`similarity_threshold` is a **soft** floor (`_soft_threshold` keeps the top few
even if all score below it — `text-embedding-3-small` cosine runs ~0.25-0.5;
default 0.15).

---

## 11. Streaming Protocol (SSE)

### Event Types (strict — frontend parses by `type` field)

> Implemented today: `agent_start`, `agent_end`, `plan`, `token`, `message_break`,
> `message_agents`, `sources`, `task_created`, `task_updated`, `tasks_archived`,
> `title`, `error`, `done` (see `core/streaming.py` + `lib/sse.ts`). `sources`
> (`{items:[{title,url}]}`) is emitted once before `done` — the dedup'd
> `intermediate_results[*].sources` (web_search etc.); the frontend renders them
> as link cards under the message and persists them to `messages.metadata.sources`
> (the synthesiser is told to cite `[1]` inline but NOT print a Sources list).
> `done` carries
> `total_tokens`, `run_id`, `langsmith_run_id?`, `title?`. `interrupt` arrives
> with its feature. The stream **always** ends with `done`, even after an
> `error` (§16). The `task_*` events carry the task dict / count from the
> `task_creator` agent — the frontend invalidates its `["tasks"]` query on them.
>
> **`message_break` / `message_agents`** — one turn can produce several assistant
> messages (a greeting, then the answer). `token` frames append to the *current*
> assistant message; `message_break` finalises it and starts the next;
> `message_agents {agents:[…]}` tags the current message with the agent(s) that
> produced it (the UI shows a small "Searching the web" / "Searched the web"
> caption above the bubble, live vs. done by whether the agent is still in
> `agent_start`/`agent_end` flight). The graph drives both: the executor emits
> `message_agents` (+ a `message_break` if not first) right before each streamed
> `segment`; the synthesiser emits them for its composed message. Each message is
> persisted as its own `messages` row with `metadata.agents` (10 ms apart via
> `add_message(created_at=)` so reload order is stable); `GET /conversations/{id}`
> returns `agents` per message.

```
data: {"type": "agent_start",   "agent": "web_search", "run_id": "..."}
data: {"type": "token",         "content": "Based on"}
data: {"type": "agent_end",     "agent": "web_search", "status": "done"}
data: {"type": "plan",          "steps": [{"id":"t1","agent":"web_search","status":"done", ...}]}
data: {"type": "message_break"}
data: {"type": "message_agents", "agents": ["web_search"]}
data: {"type": "title",         "conversation_id": "...", "title": "Learning ML"}
data: {"type": "task_created",  "task": {"id": "...", "title": "...", "status": "todo", ...}}
data: {"type": "task_updated",  "task": {"id": "...", "status": "in_progress", ...}}
data: {"type": "tasks_archived","count": 2}
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

Registry agents are dispatched by the `executor` through `AGENT_REGISTRY`.
`runner(state, task) -> AgentResult(summary, detail, sources, stream)`.
`prompt_enhancer` is a **graph node**, not a registry agent.

| Agent | File | Kind | Runs When | Output |
|-------|------|------|-----------|--------|
| Prompt Enhancer | `agents/prompt_enhancer/` | ✅ node (always, first) | every turn | `state.enhanced_query` (message rewritten self-contained) + `state.intent` label |
| Greeting | `agents/greeting/` | ✅ registered | Message is a greeting / small talk | `AgentResult.summary` (time-of-day; `state.client_hour`), `stream=True` |
| Web Search | `agents/web_search/` | ✅ registered | Current events, external facts | `intermediate_results` — Tavily results summarised + `sources` |
| Task Creator | `agents/task_creator/` | ✅ registered | "add X to my todo", "start/finish the … task", **"summarise the … task"**, "archive done", "what's on my list" | `AgentResult.summary` (`stream=True`). Parses → `TaskOps` → runs each op via the **`genie-tasks` MCP**; emits `task_created` / `task_updated` / `tasks_archived`. `summarize` emits `agent_start`/`agent_end` for a synthetic `task_summary` agent (the "Summarising the task…" pill) |
| RAG | `agents/rag/` | ⬜ stub | — | — |
| Calendar | `agents/calendar/` | ⬜ stub | — | — |

**Adding a new agent**:
1. Create `agents/<name>/agent.py` with `async def run_<name>(state: GenieState, task: TaskRecord) -> AgentResult`
2. Add an `AgentSpec` to `AGENT_REGISTRY` in `agents/registry.py` (its `description` is what the supervisor sees)
3. Write a unit test in `tests/agents/test_<name>.py`

No graph change and no prompt edit needed — the supervisor prompt is generated
from the registry.

---

## 13. Memory Architecture

> **Current reality:** only the **per-conversation** LangGraph checkpointer
> (`AsyncPostgresSaver`, `thread_id = conversation_id`) is live — it replays a
> chat's full history each turn. The **cross-conversation** L1 (Redis
> `recent_messages` / `rate_limit`) and L2 (`user_memory` hybrid search) below are
> **not built** — see **Phase 6 (§15)**. `messages`, `tasks` and the checkpointer
> tables are the only memory-ish tables that exist.

### L1 — Redis (TTL varies, ephemeral)
```
rate_limit:{user_id}:{min}    → request count (INCR/EXPIRE ~65s) — LIVE, enforced in POST /chat
recent_messages:{user_id}     → last 10 messages (LPUSH/LTRIM, TTL 2h) — Phase 6
clerk:jwks                    → Clerk JWKS JSON (TTL 1h — see Section 7.7)
user_by_clerk:{clerk_id}      → internal user UUID (TTL 5 min — see Section 7.7)
```
Note: No JWT refresh tokens in Redis. Clerk manages sessions entirely.


### L2 — Supabase PostgreSQL (permanent)
- `messages` — full conversation history. `metadata` JSONB carries `agents` / `sources` / `langsmith_run_id` / `attachments` and **`feedback`** (`"up"`|`"down"` — the user's 👍/👎, no migration). Regenerate/retry/edit hard-delete the tail (`message_repo.delete_after`).
- `conversations` — `title`, `last_message_at`, `project_id`, **`model`** (picked chat-model id; NULL → server default), **`pinned`** (sorts to top of the sidebar), **`unread`** (manual flag; cleared by `GET /conversations/{id}`), **`share_token`** (unique; NULL = private) + **`shared_at`** (frozen message cutoff for the public view). Migrations `f6703a0bb868`, `f041f866790f`, `c3d9e1f4a7b2`.
- `projects` — `instructions` + **`rag_settings`** JSONB (§10). Migration `883a87726339`.
- `attachments` — a file the user attached to one message (`kind` pdf/txt/md; `content` = extracted text). Conversation-scoped, one-shot turn context — **distinct** from `documents`. Migration `0b4ae74dbb70`.
- `documents` — a project Knowledge-Base source (`kind`, `s3_key`, `status`, `phase`, `stats`, `processed_at`). Migration `883a87726339`.
- `document_chunks` — one row per chunk: `content`, `embedding vector(1536)`, trigger-filled `fts_content`, `chunk_metadata`; `project_id` denormalized. HNSW + gin indexes (in the migration). Migration `883a87726339`.
- `tasks` — the task board (`status` todo/in_progress/done/archived; `conversation_id` FK **`SET NULL`** → the chat it was discussed in; `source_agent`; `archived_at`). Migration `bed5223f2a47`.
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
POST   /api/v1/chat                    → {run_id, conversation_id}  (body: message, conversation_id?, project_id?, model?, attachment_ids?, client_hour?)
GET    /api/v1/chat/{conv_id}/stream   → SSE stream  (query param: run_id)
POST   /api/v1/chat/{conv_id}/regenerate → {run_id, conversation_id}  (body: from_message_id, edit?) — truncate at that message + re-run; then GET …/stream
POST   /api/v1/chat/{conv_id}/confirm  → resume after calendar write interrupt
POST   /api/v1/messages/{message_id}/feedback → {vote}  (body: {vote: "up"|"down"|null}) — 👍/👎 on an assistant reply; stored in messages.metadata + best-effort LangSmith run feedback

# ── Models (Clerk JWT required) ──────────────────────────────────────────────
GET    /api/v1/models                  → {models:[{id,label,provider,hint}], default}  — the composer picker; only providers with a key

# ── Attachments (Clerk JWT required) ─────────────────────────────────────────
POST   /api/v1/attachments             → 201 {id,filename,kind,char_count,token_estimate}  (multipart: file; pdf/txt/md ≤ 5 MB; 422 on reject)
DELETE /api/v1/attachments/{id}        → 204

# ── Conversations ─────────────────────────────────────────────────────────────
GET    /api/v1/conversations           → [{id,title,created_at,last_message_at,project_id,model,pinned,unread}], pinned first then newest-activity
GET    /api/v1/conversations/{id}      → conversation + messages (+ per-message `agents` + `attachments` + `sources` + `feedback`) + project{id,name} + model + `share`{token,url,shared_at}|null; **clears `unread`**
PATCH  /api/v1/conversations/{id}      → {title?, project_id?: str|null, pinned?: bool, unread?: bool}  (only fields present are touched)
DELETE /api/v1/conversations/{id}      → 204 (cascades messages + drops the LangGraph thread)
GET    /api/v1/conversations/{id}/share  → {token,url,shared_at} | null   (owner — current public-link state)
POST   /api/v1/conversations/{id}/share  → {token,url,shared_at}   (enable; idempotent — same token; `shared_at` frozen at first share)
DELETE /api/v1/conversations/{id}/share  → 204   (disable — the link 404s; re-enabling mints a NEW token)

# ── Public (NO auth — IP rate-limited, noindex) ──────────────────────────────
GET    /api/v1/public/shared/{token}   → {title, shared_at, message_count, messages[]}  — only messages ≤ `shared_at`; whitelisted fields only (no user_id/email/project/model); 404 if unknown/revoked; 429 on abuse

# ── Projects ─────────────────────────────────────────────────────────────────
POST   /api/v1/projects                → 201 {id,name,description,instructions,...}
GET    /api/v1/projects                → [{...project, conversation_count}]
GET    /api/v1/projects/{id}           → project + its conversations
PATCH  /api/v1/projects/{id}           → update name/description/instructions/rag_settings (409 if embedding_model changes with docs)
DELETE /api/v1/projects/{id}           → 204 (CASCADE: deletes its chats + messages + threads + documents)

# ── Tasks ────────────────────────────────────────────────────────────────────
GET    /api/v1/tasks?include_archived=  → [TaskOut] (board + the Archived section)
GET    /api/v1/tasks/{id}               → TaskOut (detail modal)
POST   /api/v1/tasks   {title,desc?}    → 201 TaskOut (manual add)
PATCH  /api/v1/tasks/{id} {title?,description?,status?} → TaskOut (drag / modal edit)
POST   /api/v1/tasks/{id}/summarize     → TaskOut  (LLM-summarise its linked chat → description)
POST   /api/v1/tasks/archive-done       → {archived: N}  (done → archived; the button)
DELETE /api/v1/tasks/{id}               → 204
# chat-driven moves ("start the report task", "summarise this task") go via the task_creator agent → the tasks MCP

# ── Documents (project Knowledge Base — §10) ─────────────────────────────────
POST   /api/v1/documents               → 201 DocumentOut  (multipart: project_id + file; pdf/md/txt ≤ 25 MB → S3 → SQS)
GET    /api/v1/documents?project_id=    → [DocumentOut]  (status/phase/stats/chunk_count)
GET    /api/v1/documents/{id}           → DocumentOut
GET    /api/v1/documents/{id}/stream    → SSE  (live ingestion pipeline progress — relays redis doc_pipeline:{id})
GET    /api/v1/documents/{id}/chunks    → [ChunkOut]  (chunk_index, content, token_count, metadata)
DELETE /api/v1/documents/{id}           → 204 (S3 object + chunks + row)
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
- [x] `GenieState` TypedDict (+ `TaskRecord` ledger) + `SupervisorPlan` Pydantic model
- [x] Supervisor node with `with_structured_output(SupervisorPlan)` — registry-driven, no hardcoded routing; produces a task ledger; capped re-plan loop
- [x] Agent registry (`agents/registry.py`) + `executor` node (sequential, dep-ordered, `agent_start`/`agent_end`/`plan` events)
- [x] Web Search agent (Tavily) — grounded summary + sources
- [x] Greeting agent — time-of-day greeting from `client_hour`
- [x] Prompt Enhancer node — first node; rewrites the latest message self-contained (resolves pronouns) + an `intent` label → `state.enhanced_query`
- [x] Synthesiser node — composes the one streamed reply (greeting fast-path skips the LLM)
- [x] Validator node — non-empty check + an LLM grounding check when agents ran; a reject re-plans (capped)
- [x] `AsyncPostgresSaver` checkpointer wired (session-mode URL) — compiled with `build_graph()` (prompt_enhancer→retriever→supervisor→executor→synthesiser→validator)
- [x] `POST /chat` (+ `client_hour`) + `GET /chat/{id}/stream` SSE endpoints
- [x] SSE event protocol: `agent_start`, `agent_end`, `plan`, `token`, `message_break`, `message_agents`, `task_*`, `title`, `error`, `done` emitted
- [x] Redis L1: `rate_limit` — `memory/short_term.check_rate_limit` (INCR/EXPIRE), enforced in `POST /chat` (429). _`recent_messages` → Phase 6._
- [x] LangSmith tracing — `configure_tracing()` in the lifespan pushes `LANGSMITH_*` into `os.environ`; each chat turn's root run id is stored on the assistant message's `metadata.langsmith_run_id` and echoed in the SSE `done` event. Verified: traces land in the LangSmith project.
- [x] Circuit breaker on LLM calls — `agents/models.ainvoke()` (tenacity, 3 attempts, exponential backoff on transient OpenAI errors); used by every non-streaming call. Streaming calls keep langchain's own retry.
- [x] Token-usage write-back — `prompt_enhancer` / `supervisor` / `synthesiser` / `validator` accumulate `GenieState['token_usage']` (via `models.tokens_of` / `bump_tokens`), so the supervisor's `MAX_TOKENS_PER_RUN` guard bites on re-plan.

**Frontend tasks**:
- [x] Next.js **15** App Router scaffold + Tailwind v3 + shadcn/ui conventions (`components.json`, `ui/button`)
- [x] Install `@clerk/nextjs` (v7), `NEXT_PUBLIC_CLERK_*` via Clerk CLI, `<ClerkProvider>` in `<body>`
- [x] Route protection — _resource-based `await auth()` in `(app)/layout.tsx` (v7 style), not middleware matcher; `middleware.ts` runs bare `clerkMiddleware()`_
- [x] Sign-in page (`/sign-in/[[...sign-in]]`) and sign-up page using Clerk `<SignIn />` / `<SignUp />`
- [x] After sign-up: `<SignUp forceRedirectUrl="/welcome">` → `app/welcome/page.tsx` polls `GET /users/me` until 200, then → `/chat` (webhook race guard, §7.8)
- [x] Chat page: `ChatWindow`, `Message`, `StreamingDot` — _streams live tokens; input disabled mid-turn_
- [x] `useChat` hook: POST /chat → SSE connection → append tokens; rehydrates from `GET /conversations/{id}` on reload
- [x] `AgentActivity` component — renders `chatStore.activeAgents` from live `agent_start`/`agent_end` SSE events
- [x] Zustand `chatStore`: messages, activeAgents, runId, conversationId
- [x] Conversation sidebar — `useConversations` list (recency-ordered), "New chat", `/chat/[id]` per conversation, auto-title (cheap-LLM, SSE `title` event), delete
- [x] Plan strip (`components/chat/PlanStrip.tsx`) — renders the `plan` SSE event: numbered steps + per-step status icon; cleared on the next send

**Database tasks**:
- [x] Run `setup_supabase.sql` (extensions, hybrid-search RPCs; indexes/RLS deferred to Phase 2)
- [x] Alembic migrations: `1c61bba11678` (users/conversations/messages, genie schema), `34e9ccc89880` (conversations.last_message_at), `84a8e112e61f` (projects + conversations.project_id), `f6703a0bb868` (conversations.model)
- [x] Verify LangGraph checkpointer tables created by `checkpointer.setup()`

**Phase 1 done when**: User can sign up via Clerk (Google or email), is auto-synced to the `users` table, send a message, see "web_search is thinking…" animate, receive a streamed response using live web data, and the conversation persists across page reload. — **✅ met** (2026-09-01). Remaining polish (circuit-breaker tuning, per-user token quotas) tracked in later phases.

---

### PHASE 2 — Tasks + RAG / Documents (Weeks 4–6)
**Goal**: Genie manages a task board and can answer from the user's own documents.
_(Cross-conversation memory moved to **Phase 6** — the conversation checkpointer
already gives per-chat memory.)_

**Backend tasks**:
- [x] Task Creator agent — registered; parses → `TaskOps` → **`genie-tasks` FastMCP** (§22) → `task_created`/`task_updated`/`tasks_archived` SSE
- [x] Alembic migration: `tasks` table (`bed5223f2a47`); `task_repo` + `task_service` + `/tasks` REST + `app/mcp/tasks_server.py`
- [x] **Composer attachments** (`0b4ae74dbb70`) — `attachment_service` parses pdf/txt/md → text → the `attachments` table → one-shot into the turn's prompts. The parser + `attachments.content` are the stepping stone for the ingestion pipeline below (chunk + embed the stored text).
- [x] **Project Knowledge Base — commit 1 (ingestion)** (`883a87726339`) — `documents` + `document_chunks` (pgvector `vector(1536)` + ivfflat + gin + fts trigger) + `projects.rag_settings`; `core/aws.py` (S3/SQS, LocalStack-auto); `document_service` (validate → S3 → SQS); `ingestion_worker` (partition via pdfminer/unstructured → `chunk_by_title` → OpenAI embeddings → bulk store, Redis progress, idempotent); `POST/GET/DELETE /documents` + `/{id}/stream` + `/{id}/chunks`; `PATCH /projects/{id} {rag_settings}` (409-locked embedding model)
- [x] **Project Knowledge Base — commit 2 (retrieval)** — `retrieval_service` (vector / hybrid RPC / multi-query + RRF); `retriever` graph node (`prompt_enhancer → retriever → supervisor`) gated by `has_kb` + the enhancer's `needs_documents`; `_kb_note` → supervisor, `_format_kb` → synthesiser. `hybrid_search_project_chunks` RPC in `setup_supabase.sql`. Verified live end-to-end (embeddings faked — OpenAI at $0).

**Frontend tasks**:
- [x] Task Board: `/tasks` — 3 columns, HTML5 drag between columns, "Archive done" button, collapsible "Archived (N)"
- [x] Task detail modal — status, linked chat (`/chat/<id>`), editable description, "Summarise from chat", delete
- [x] `useTasks` / `usePatchTask` / `useArchiveDone` / `useDeleteTask` / `useSummarizeTask`; `useChat` invalidates `["tasks"]` on the `task_*` SSE events
- [x] **Knowledge Base panel** in `ProjectView` — `DocumentUpload` (drag-drop, parallel), `DocumentList` (status pills, polls while ingesting), `PipelineModal` (live SSE: Upload→Partition→Chunk→Vectorize→Store→Chunks, "Elements Discovered", per-step state), `ChunkViewer`, `RagSettingsForm` (embedding model locked + strategy + param sliders)

**Phase 2 done when**: Tasks are managed by chat + the board (✅). A project has a
Knowledge Base: files upload → the pipeline processes them visibly → chunks are
browsable (✅ commit 1); a chat in that project answers grounded in the KB
(commit 2). _Deferred to a backlog: multimodal RAG (images/tables as vectors),
"Paste website URL" ingestion, per-chunk contextual summarisation, the RAG
routing agent (`agents/rag/`)._

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
- [ ] Token budget enforcer in supervisor (check `state.token_usage` before routing)
      _(memory-consolidation worker → Phase 6)_

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

- [x] Per-conversation model selection — `MODEL_CATALOG` (OpenAI/Anthropic/Groq), `GET /models`, composer picker, `conversations.model` (2026-09-01)
- [x] Rich response rendering — synthesiser = response drafter (`RESPONSE_FORMAT_GUIDE`); frontend `Markdown.tsx` (react-markdown + GFM + rehype-highlight) with copyable, syntax-highlighted code blocks (2026-09-02). Backlog: KaTeX math, Mermaid diagrams, streaming re-parse debounce.
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

### PHASE 6 — Memory: short-term + long-term (not started — deferred)

**Goal**: Genie remembers the user *across* conversations — recent activity and
durable, learned facts / preferences.

**Why it's a phase, not a hack**: the LangGraph `AsyncPostgresSaver` checkpointer
(`thread_id = conversation_id`) already gives full **per-conversation** memory.
Everything below is the *cross-conversation* layer, which is currently all stubs
(`app/memory/*`, `services/memory_service.py`, `db/repositories/memory_repo.py`,
`workers/memory_consolidation.py` all `raise NotImplementedError`; `user_memory`
table not migrated; `GenieState.user_memories` always `[]`). The
`hybrid_search_memories` RPC already exists in `scripts/setup_supabase.sql`.

**Two layers (CLAUDE.md §13)**
- **Short-term (STM)** — recency-ordered, ephemeral, per user, cross-chat.
  Redis, `user_id`-keyed, ~2h TTL. "What has this person been doing lately."
  Injected wholesale.
- **Long-term (LTM)** — relevance-ranked, durable, *learned* facts & preferences.
  Postgres `user_memory` (`embedding vector(1536)` + `fts_content tsvector`),
  hybrid (RRF) search; only the top ~5 injected. "What is always true about
  this person."

**Use cases (our product specifically)**
- Standing facts so agents stop asking: home city / timezone (greeting +
  web_search "weather" with no "where?"), employer, role, the products worked on,
  key people.
- Response-style prefs feeding the **synthesiser**: "code only, no preamble",
  "TypeScript examples", expertise level, don't-re-explain.
- **Supervisor** routing hints ("this user asks about their docs a lot" → RAG).
- Cross-conversation continuity ("last week we decided X" surfaced in a new chat).
- Task intelligence for `task_creator`: recurring tasks, typical priorities,
  "weekly review on Fridays"; STM fixes `_resolve_task_id` so "mark it done"
  works about a task discussed in a *different* chat.
- Rate limiting (`rate_limit:{user_id}:{min}`) lives in `memory/short_term.py`.

**Staged plan (build in this order — cheapest / lowest-risk first)**
1. **STM.** Implement `memory/short_term.py` (`recent_messages` LPUSH/LTRIM,
   `rate_limit` INCR/EXPIRE) + `memory/manager.load_context()` (Redis only for
   now) → wire into `chat_service._generate` → new `GenieState` field →
   supervisor / synthesiser prompts get a "recent activity" block. Push every
   user + assistant message into STM.
2. **Explicit LTM (Claude/ChatGPT model — user-controlled, no magic).** Migrate
   `user_memory`; wire embeddings (`text-embedding-3-small`) + the
   `hybrid_search_memories` RPC via `memory_repo`; a **`remember` MCP tool** (fits
   the §22 layer — "remember that I…") + a `/memory` settings page to view/edit/
   delete. `load_context()` adds hybrid search → `GenieState.user_memories` →
   prompts.
3. **Automatic consolidation.** After each turn, a fire-and-forget LLM extraction
   of durable facts → embed → upsert (skip the SQS worker until scale; keep it
   idempotent per CLAUDE.md §4.5). Everything it learns is visible + editable on
   `/memory`.
4. **Refinements (was Phase 5):** importance scoring (LLM rates facts 0–1,
   `importance` column) and decay (down-weight old facts in the hybrid ranking).

**Phase 6 done when**: a fact stated in one chat ("I only want TypeScript
examples") changes the next chat's answers; "the task I just made" resolves in a
brand-new chat; `/memory` lets the user see and remove what Genie knows.

---

## 16. Testing Strategy

### Unit Tests (per agent, per service)
```
tests/  (≈90 tests, all green)
├── agents/
│   ├── test_supervisor.py      ← plan validation, executor dep-order, validator, routing, attachment + KB helpers, retriever gate
│   ├── test_registry.py        ← registry integrity
│   ├── test_models.py          ← ainvoke retry, bump_tokens, MODEL_CATALOG resolve/filter
│   ├── test_prompt_enhancer.py ← rewrite + token track + passthrough/error
│   ├── test_greeting.py        ← time buckets + LLM/template fallback
│   ├── test_web_search.py      ← Tavily mocked, summary + sources
│   ├── test_task_creator.py    ← create / move / summarise (task_summary pill) / archive
│   ├── test_rag.py / test_calendar.py  ← Phase 2/3
├── mcp/
│   └── test_tasks_server.py    ← in-memory Client, task_service faked
├── services/
│   ├── test_chat_service.py    ← SSE framing, message splitting
│   ├── test_task_service.py    ← create / move / archive_done / summarise
│   ├── test_attachment_service.py ← parse_upload: txt/md/pdf, reject bad type / oversize / empty
│   ├── test_partition_service.py  ← md/txt/pdf → typed elements + stats
│   ├── test_chunk_service.py      ← chunk index/tokens/metadata; size affects count
│   ├── test_document_service.py   ← create_and_enqueue: S3 put + SQS send; reject bad type/oversize
│   └── test_retrieval_service.py  ← strategy dispatch (vector/hybrid/multi-query) + RRF fusion
├── schemas/
│   └── test_rag_settings.py    ← defaults / clamping / enum / resolve
├── workers/
│   └── test_ingestion_worker.py ← ingest_document happy path / idempotent skip / failure → failed
├── memory/
│   └── test_short_term.py      ← rate limiting (window + user isolation)
└── api/
    ├── test_webhooks.py · test_users_me.py · test_conversations.py (+ PATCH project) · test_sharing.py
    ├── test_projects.py (+ rag_settings merge/409) · test_tasks.py · test_health.py
    ├── test_models_endpoint.py · test_attachments.py · test_documents.py
```

### Key Test Assertions
- Supervisor never emits an exact `(agent, description)` step twice; an agent may recur for genuinely distinct sub-tasks (plan capped at 6)
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

# Logging — structlog, structured, every meaningful step (full policy in §21)
logger = structlog.get_logger(__name__)
logger.info("agent_run_done", agent="web_search", duration_ms=1240, sources=5)
# user content → preview(text) or chars=len(text), never raw. Secrets are
# auto-scrubbed by core/logging.py:redact_processor but don't log them on purpose.
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
| `if "calendar" in query: route_to_calendar()` | LLM-based routing via `SupervisorPlan` (registry-driven) |
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

_Last updated: 2026-09-01 — **Phase 1 closed out**: `prompt_enhancer` node (rewrites the message self-contained + `intent`, resolves pronouns), an LLM circuit breaker (`models.ainvoke` — tenacity backoff on all non-streaming calls), Redis `rate_limit` enforced in `POST /chat` (429), a real validator grounding check when agents ran, `token_usage` write-back so the budget guard bites, the post-sign-up `/welcome` gate polling `GET /users/me`, and the `PlanStrip` rendering the `plan` SSE event._

_Also 2026-09-01 — **LLM provider switch** (`settings.LLM_PROVIDER` = `openai` | `groq`): `agents/models.py` builds `ChatGroq` or `ChatOpenAI`; `config.chat_model_name` / `utility_model_name` / `llm_configured` resolve by provider; `_transient_errors()` collects both SDKs' retryable exceptions; `title_service` + `task_service._summarise` now route through the shared factories. Verified live end-to-end through the real graph with `LLM_PROVIDER=groq` (`openai/gpt-oss-120b` + `openai/gpt-oss-20b`) — structured output (`include_raw`), `usage_metadata` token write-back, and streamed synthesiser tokens all work; `ainvoke` retry bumped to 4 attempts / ~30s to ride out the Groq free-tier 8k-TPM 429. Embeddings stay on OpenAI._

_Also 2026-09-01 — **Groq reasoning-model fix + utility model → `qwen/qwen3.8-27b`**: Groq's `openai/gpt-oss-*` and `qwen/qwen3*` burn completion tokens on a hidden reasoning pass before emitting content, so a tight `max_tokens` returns an empty string (`finish_reason="length"`) — this silently broke auto conversation titles. `models._build(light=True)` (always set by `get_utility_model()`) now sends the smallest valid `reasoning_effort` per model family (`_groq_light_reasoning()`: `"low"` for gpt-oss — it rejects `"none"` — `"none"` for qwen3); `title_service` `max_tokens` 24 → 64. `GROQ_UTILITY_MODEL` is now `qwen/qwen3.8-27b` (follows a terse system prompt better than gpt-oss-20b; verified titles + structured output + the full graph). Any new tight-budget utility call must still leave a little headroom for the pass._

_Also 2026-09-01 — **Model picker + unified multi-provider LLM layer**: `MODEL_CATALOG` in `agents/models.py` (8 models across OpenAI · Anthropic · Groq); `_build(provider, model, …)` covers all three (`langchain-anthropic` added — the Anthropic branch omits `temperature` since Claude 5 models 400 on it, defaults `max_tokens` 8192, sends `anthropic-workspace-id` from `ANTHROPIC_WORKSPACE_ID` when set). `get_chat_model(model_id=…)` → `resolve_model_spec` (unknown / keyless id → server default, logged). `GenieState['model']`, `conversations.model` (migration `f6703a0bb868`), `POST /chat` `model?`, new `GET /api/v1/models`. Composer `ModelPicker` (`useModels`, `chatStore.model`, per-conversation + `localStorage` default for new chats). Only the **chat** model is picked — the utility model is unchanged. Verified: catalog resolution, the graph threading a per-call model, and the picker via the frontend build. NB: the current `ANTHROPIC_API_KEY` is identity-linked and needs `ANTHROPIC_WORKSPACE_ID` set for the Claude options to actually call._

_Also 2026-09-01 — **Composer "+" menu: file attachments + Add to project**: `POST /attachments` (multipart, pdf/txt/md ≤ 5 MB) → `attachment_service.parse_upload` (`pypdf` for PDF; utf-8 for txt/md) → `attachments` table. `POST /chat` `attachment_ids` → `create_turn` links them to the user message (+ `message_metadata.attachments`) → `_generate` → `GenieState['attachments']` (**one-shot** — that turn only). `nodes._attachment_note` (filenames) → enhancer + supervisor (skip web search); `nodes._format_attachments` (24k-char budget, visible `…[truncated]`) → synthesiser only. New `PATCH /conversations/{id} {project_id}`. Frontend: `PlusMenu` (Add files hidden `<input>` · Add to project submenu → `patchConversation` or `chatStore.pendingProjectId` for a new chat), `AttachmentChips`, `useAttachments`, `chatStore.pendingAttachments`. Verified live: small file → supervisor plans empty (no web search), synthesiser answers from it; 30k-char file → truncation marker, run stays well under `MAX_TOKENS_PER_RUN`._

_Also 2026-09-01 — **Project Knowledge Base, commit 1 (ingestion pipeline)**: `documents` + `document_chunks` (pgvector `vector(1536)`, ivfflat + gin + fts trigger) + `projects.rag_settings` (migration `883a87726339`). `core/aws.py` (boto3 s3/sqs, LocalStack auto-provisions bucket + queue on boot). `POST /api/v1/documents` (multipart, pdf/md/txt ≤ 25 MB) → `document_service` uploads to S3 + enqueues SQS. `workers/ingestion_worker.py` (dev: in-process from the lifespan; prod: `python -m`) polls SQS → `ingest_document` runs `partition_service` (pdfminer for PDF, `unstructured` for md/txt → typed Elements + "Elements Discovered" stats) → `chunk_service` (`chunk_by_title`, size/overlap from `RagSettings`) → `embedder.embed_batch` (**OpenAI `text-embedding-3-small`**) → `document_chunk_repo.bulk_insert`; idempotent (skips `ready`/`processed_at`); per-phase status on the row + `redis PUBLISH doc_pipeline:{id}`. `GET /documents/{id}/stream` (SSE) relays it; `/{id}/chunks` browses them. Frontend: `KnowledgeBasePanel` in `ProjectView` (Documents + Settings tabs) — `DocumentUpload`, `DocumentList`, `PipelineModal` (live), `ChunkViewer`, `RagSettingsForm`. Verified end-to-end against LocalStack + Postgres (embeddings faked — the OpenAI account is at $0; the vectorize phase needs a top-up)._

_Also 2026-09-01 — **Project Knowledge Base, commit 2 (retrieval)**: `services/rag/retrieval_service.retrieve()` — `vector` (pgvector cosine + threshold) / `hybrid` (`hybrid_search_project_chunks` RPC, RRF) / `multi_query_*` (utility-model paraphrases → per-query search → RRF-fuse → top `final_context_size`). New **`retriever` graph node** (`prompt_enhancer → retriever → supervisor`), a pipeline node (not a registry agent), runs only when `state.has_kb and state.needs_documents`; `EnhancedPrompt` gained `needs_documents` (the enhancer's gate — false for greetings/small talk). `nodes._kb_note` (filenames) → supervisor; `nodes._format_kb` (chunks, 12k-char budget) → synthesiser via `_augment_system`. `GenieState` += `rag_settings` / `has_kb` / `needs_documents` / `retrieved_chunks`; `chat_service._generate` loads them from the project. Frontend labels `kb_search`. Verified live through the graph: "how does retrieval work?" in a KB project → enhancer flags it → 5 chunks retrieved → grounded answer; "hi there" → gate off, skipped._

_Also 2026-09-01 — **KB retrieval hardening** (bug: a real CV upload answered from a web search instead of the doc). Root causes: (1) **ivfflat index has ~0 recall on a small per-project table** → migration `344f477b87da` swaps it for **HNSW**; (2) `similarity_threshold=0.3` filtered out every real hit (`text-embedding-3-small` cosine runs ~0.25-0.5) → default → 0.15 and `_soft_threshold` keeps the top few regardless; (3) the retriever didn't appear in the plan and the supervisor still planned `web_search` → the retriever now seeds a completed `knowledge_base` ledger step, `supervisor_node` merges it, and `_kb_note` instructs "return an EMPTY plan — no web_search for anything a document could hold". Verified against the real "Resume KB" project: "tech stacks manjeet is expertised in" → plan `[knowledge_base]`, grounded answer; "hi hello" → `[greeting]`, KB untouched._

_Also 2026-09-01 — **supervisor plan crash guard**: Groq's `with_structured_output(SupervisorPlan, include_raw=True)` intermittently returns `parsed=None` (emits `steps: null` / drops `rationale`). `supervisor_node` now guards `plan_out is None` (→ answer directly, keeping the `knowledge_base` step); `SupervisorPlan` has a `@field_validator("steps", mode="before")` coercing `None`→`[]` and a default `rationale`._

_Also 2026-09-02 — **chat UI redesign** (Claude-inspired): (1) **`ChatHeader`** — sticky top bar with the conversation title + a ▾ menu: **Rename** (→ `PATCH /conversations/{id} {title}`, which now merges only the fields present), **Add to project** submenu, **Delete**; the project chip moved here. (2) **Sidebar** drag-to-resize (right-edge handle, 220-460 px, `localStorage["genie.sidebar_w"]`). (3) **`Message`** — the user's messages sit in a subtle right-aligned box; **Genie's have no bubble/border and blend into the page**. (4) **`SourceCards`** — `sources` SSE event (`{items:[{title,url}]}`, emitted once before `done` from the dedup'd `intermediate_results[*].sources`) → link cards under the message; persisted to `messages.metadata.sources` and returned by `GET /conversations/{id}`; the synthesiser is told to cite `[1]` inline but not print a Sources list. Verified live: a web_search turn emits 5 source cards, no trailing "Sources:" text._

_Also 2026-09-02 — **message actions (regenerate / retry / edit · 👍👎 · copy · date)**: `POST /chat/{id}/regenerate` (`{from_message_id, edit?}`) → `chat_service.regenerate_turn` picks the anchor user message (before an assistant target, or the target itself; `edit` replaces its text via `message_repo.set_content`), `message_repo.delete_after(anchor.created_at)`, `checkpointer.adelete_thread(cid)`, stashes a `mode="regenerate"` Redis run; `_generate` replays the surviving `messages` rows as `state["messages"]` (thread just reset → no double-merge), then streams + persists as normal. New `endpoints/messages.py` → `POST /messages/{id}/feedback {vote}` → `message_repo.set_feedback` (into `messages.metadata.feedback`, no migration) + best-effort `observability.send_run_feedback` (LangSmith `user_thumbs` on `metadata.langsmith_run_id`). `MessageOut.feedback` added. Frontend: `MessageActions.tsx` (always-visible subtle row — Copy · 👍👎 · Regenerate on replies; date · Retry · Edit · Copy on user messages), `Message.tsx` inline-edit textarea (⌘/Ctrl+Enter to submit) + `"use client"`; `useChat` gains `regenerate` / `voteMessage` / a shared `consumeStream` + `refreshMessages` (swaps optimistic ids for persisted rows so a follow-up regenerate works). `chatStore` `ChatMessage` += `createdAt` / `feedback`; `truncateAfter` / `updateMessageContent` / `setMessageFeedback`. Public `/share` page shows the date only (no buttons). Verified: 148 backend tests, ruff + build/lint clean._

_Also 2026-09-02 — **business-document draft card**: `DOCUMENT_BLOCK_GUIDE` (`agents/supervisor/prompts.py`, appended to both user-facing prompts) tells the drafter to emit a ```` ```document ```` fence — `key: value` metadata (`kind:` from email|letter|application|cover-letter|memo|proposal|message|agenda|note; `subject:` / `to:` for mail), a `---`, then the Markdown body — whenever the user asks it to WRITE a business communication (not for code / "how to write" advice / outlines). Frontend `components/chat/DocumentCard.tsx`: `Markdown.tsx`'s `pre` handler routes a `language-document` block (rehype-highlight `plainText: ["document"]` keeps the class, no tokenising) to a boxed card — kind icon + label header, `Subject:` / `To:` row, **Copy** button (`Subject: …\n\n` + body for mail), body via a nested `<Markdown>`. Streaming-safe (before `---` arrives the whole block is the body). Single draft for now — A/B/C variant tabs + Gmail/mailto send deferred. Verified: SSR smoke test (class kept, no `hljs` spans), 140 backend tests, build/lint clean._

_Also 2026-09-02 — **rich response rendering + synthesiser-as-drafter**: `RESPONSE_FORMAT_GUIDE` (`agents/supervisor/prompts.py`) appended to `SYNTHESISER_SYSTEM_PROMPT` + `CHAT_SYSTEM_PROMPT` — one spec telling the model to choose the lightest structure and use GFM (styled headings only when long, pipe tables, fenced code with an explicit language tag for every code/query/config/command, inline code, blockquote caveats, `[1]` citations, no "Sources" list). No separate formatting pass — still one streamed synthesiser call. Frontend: `components/chat/Markdown.tsx` (`react-markdown` v9 + `remark-gfm` + `rehype-highlight`) + `CodeBlock.tsx` (language label + Copy button over the hljs-tokenised `<pre>`); `Message.tsx` renders Genie replies through it (user messages stay plain text). `globals.css` gains `--code-*` / `--hl-*` vars + `.hljs-*` rules so code themes follow light/dark with no JS. Deliberately **no `rehype-raw`** (no raw-HTML → zero XSS surface); `javascript:` links render inert. `/chat` bundle +~93 KB. KaTeX + Mermaid deferred. Verified: SSR smoke test (table + `hljs language-sql` spans + blockquote), 140 backend tests, ruff + frontend build/lint clean._

_Also 2026-09-02 — **chat share (public view link) + chat-scroll shadow**: `conversations.share_token` (unique) + `shared_at` (migration `c3d9e1f4a7b2`). Owner routes `GET/POST/DELETE /conversations/{id}/share` (`conversation_repo.set_share` / `clear_share` / `get_by_share_token`; token = `secrets.token_urlsafe(16)`, 128-bit; POST idempotent — returns the existing token; `shared_at` frozen at first share, re-enabling mints a new token). New **unauthenticated** `endpoints/public.py` → `GET /api/v1/public/shared/{token}`: IP-rate-limited (reuses `check_rate_limit`), `Cache-Control: public, max-age=60` + `X-Robots-Tag: noindex`, returns only messages with `created_at <= shared_at` and a **whitelist** (`title`, `role`, `content`, `agents`, `sources`, attachment `filename`/`kind`) — never `user_id` / email / project / model. Frontend: `ShareChatModal` (Keep private ↔ Create public link + Copy link) from the new **Share** button in `ChatHeader`; `useShareConversation` (`["share", id]` query + enable/disable). Public page `app/share/[token]/page.tsx` (+ `not-found.tsx`) — server component, outside `(app)`, `robots: noindex`, reuses `<Message>`; `SourceCards` now only renders an `<a>` for `http(s)` URLs. `FRONTEND_BASE_URL` setting builds the absolute share URL. Chat-scroll shadow: `useScrollShadow` → `ChatHeader` gets a bottom shadow when `!atTop`, the composer a top shadow when `!atBottom`. Sidebar-resize scrim: `useSidebarWidth` exposes `isDragging` → a `fixed inset-0` `backdrop-blur` scrim over the app + `shadow-2xl` on the `<aside>` + a lit handle line while dragging. `Modal` backdrop gains `backdrop-blur-sm`. Verified: 139 backend tests, ruff + frontend build/lint clean._

_Also 2026-09-02 — **pinned chats + read/unread**: `conversations.pinned` / `conversations.unread` Boolean columns (migration `f041f866790f`). `conversation_repo.list_for_user` orders `pinned DESC, last_message_at DESC NULLS LAST`; new `set_flag(**bools)` + `mark_read()`. `GET /conversations/{id}` clears `unread` on open; `PATCH /conversations/{id}` accepts `pinned?` / `unread?`. `ConversationSummary` carries both. Frontend: `ChatHeader` refactored onto the new shared **`ConversationMenu`** (⋯ dropdown — Pin/Unpin · Mark read/unread · Rename · Add-to-project submenu · Delete) with a pin glyph on the title trigger; `Sidebar` splits the list into a **Pinned** section then **Chats**, each row showing a read/unread bullet (filled `bg-brand` = unread) and the same `ConversationMenu` on hover + inline rename. `useChat` marks a chat read locally on open and invalidates the sidebar list._

| Phase | Status | Completion |
|-------|--------|-----------|
| Phase 0 — Scaffold | 🟢 Complete | 100% |
| Phase 1 — Foundation | 🟢 Complete | 100% |
| Phase 2 — Tasks + RAG / Documents | 🟢 Complete | 100% (tasks ✅, KB ingestion + retrieval ✅) — multimodal/website/RAG-agent → backlog |
| Phase 3 — Calendar + Async | 🔴 Not Started | 0% |
| Phase 4 — Infrastructure | 🔴 Not Started | 0% |
| Phase 5 — Expansion | 🔴 Not Started | 0% |
| Phase 6 — Memory (STM + LTM) | 🔴 Not Started (deferred) | 0% |

### 19.1 Implementation ledger

**Backend** (`@clerk/…` n/a — FastAPI + uv; deps in `backend/requirements.txt`)
- ✅ App factory + lifespan (`main.py`): Redis ping, DB `SELECT 1`, `AsyncPostgresSaver.setup()` (non-fatal in dev)
- ✅ `config.py` (pydantic-settings, all §6 vars), `core/middleware.py` (`request_id` + request lifecycle logs), `core/exceptions.py`, `core/redis.py`, `core/streaming.py` (SSE frame helper)
- ✅ **Application-wide logging** (§21) — `core/logging.py`: `structlog` (console in dev, JSON in prod), a `redact_processor` that scrubs secrets from every event, `preview()` for user content, noisy libs pinned to WARNING. Step logs across middleware, `core/clerk*`, `services/chat_service.py`, `agents/supervisor/nodes.py`, the greeting/web_search agents, `db/repositories/*`, `db/session.py`, and the `main.py` lifespan. **Datadog agent = pending.**
- ✅ **LangSmith tracing** — `core/observability.py:configure_tracing()` (called first in the lifespan) copies `LANGSMITH_*` from Settings into `os.environ` so LangChain actually traces; each chat turn's root run id → `messages.metadata.langsmith_run_id` + the SSE `done` event.
- ✅ `GET /health`, `GET /health/ready` (Redis + DB checks)
- ✅ **Chat**: `POST /chat` (persist user msg + stash run — incl. `client_hour` — in Redis) → `GET /chat/{id}/stream` SSE. Runs the real **supervisor graph** (`build_graph`: `supervisor → executor → synthesiser → validator`, capped re-plan loop) compiled with a live `AsyncPostgresSaver` checkpointer held in the lifespan; `thread_id = conversation_id`. `chat_service._generate` streams only the synthesiser's tokens, relays `agent_start`/`agent_end`/`plan` custom events as SSE, accumulates token usage, and falls back to `graph.aget_state` for the greeting fast-path (no streamed tokens). Both messages persist to `messages`.
- ✅ `GET /conversations`, `GET /conversations/{id}` (conversation + messages); `conversation_repo` / `message_repo` real methods
- ✅ **Clerk auth** (`core/clerk.py`): JWKS fetched from the Frontend API host (derived from `CLERK_PUBLISHABLE_KEY`, or explicit `CLERK_DOMAIN`), Redis-cached (`clerk:jwks`); `RS256` verify; `sub` → internal user via Redis `user_by_clerk:{id}` → `UserRepository` → auto-provision (`create_from_clerk_token`, email/name enriched from the Clerk Backend API). `touch_last_active`. Dev-user fallback **only when no Clerk domain is configured**.
- ✅ `POST /webhooks/clerk` — Svix-verified; `user.created/updated/deleted` → `UserRepository`. Local: `clerk webhooks --forward-to …`. `user_repo` Clerk helpers all implemented.
- ✅ Dev user row seeded on startup **only when Clerk is unconfigured**
- ✅ Remaining §14 endpoints still return **501** (`/tasks`, `/documents`, `/chat/{id}/confirm`, `DELETE /conversations/{id}`)
- ✅ SQLAlchemy models `users` / `conversations` / `messages` + first Alembic migration (`1c61bba11678`, applied). Phase 2+ models are inert placeholder files.
- ✅ **Supervisor orchestration** (`agents/supervisor/{state,nodes,graph,prompts}.py` + `agents/{base,models,registry}.py`) — `SupervisorPlan` structured output → validated task **ledger** (`TaskRecord[]` in `GenieState`: id / agent / status / depends_on / result). The prompt tells it to split every intent into its own step (a greeting **and** a request → two steps; several research needs → several `web_search` steps). `executor` runs the steps **sequentially** in dependency order through `AGENT_REGISTRY`, keying `intermediate_results` by task id; a later agent sees earlier results. `AgentResult(stream=True)` outputs (greeting; `AgentSpec.stream`) are emitted as a `segment` event and become their **own** captioned assistant message; the graph emits `message_break`/`message_agents` around each message, the `synthesiser` composes only the request answer into the last one (told the greeting was already sent). One turn → several `messages` rows with `metadata.agents` (`add_message(created_at=)` keeps them ordered). `validator` minimal (approves non-empty); `route_after_validator` re-plans up to `SUPERVISOR_MAX_TURNS` (default 2).
- ✅ **prompt_enhancer node** — runs first: `get_utility_model().with_structured_output(EnhancedPrompt, include_raw=True)` rewrites the latest message self-contained (resolves "it"/"the second one") → `state.enhanced_query` + `state.intent` + `state.needs_documents` (the KB retrieval gate); passthrough on any error; emits `agent_start`/`agent_end` for the "Understanding your request…" pill.
- ✅ **retriever node** (`nodes.retriever_node`, §10) — `prompt_enhancer → retriever → supervisor`. A pipeline node, not a registry agent. No-op unless `state.has_kb and state.needs_documents`; else opens its own session → `retrieval_service.retrieve(project_id, enhanced_query, RagSettings)` → `state.retrieved_chunks`. `kb_search` pill. `_kb_note` → supervisor, `_format_kb` → synthesiser.
- ✅ **Unified LLM layer + model picker** (`agents/models.py`) — `MODEL_CATALOG` (8 models · OpenAI/Anthropic/Groq); `_build(provider, model, …)` → `ChatOpenAI` / `ChatAnthropic` / `ChatGroq`; `get_chat_model(model_id=…)` → `resolve_model_spec` (unknown/keyless → `_default_spec()` = `LLM_PROVIDER` + `chat_model_name`, logged `model_id_unresolved`). The 4 chat-model call sites (`supervisor` / `synthesiser` ×2 / `web_search` / `task_creator`) pass `model_id=state.get("model")`; `get_utility_model()` untouched. `conversations.model` persists the pick (`chat_service.create_turn` sets/updates it; `_generate` → `GenieState['model']`). `GET /api/v1/models` lists the catalog filtered to configured providers. `ainvoke()` = tenacity `AsyncRetrying` (4 attempts, `wait_exponential(2..30s)`) on `openai` / `anthropic` / `groq` transient errors (dynamic `_transient_errors()`); streaming keeps langchain's `max_retries=2`. `tokens_of()` + `bump_tokens()` → `token_usage.by_agent` per node.
- ✅ **Validator** (`nodes.validator_node`) — reject if empty; else, **only when agents produced findings**, an LLM grounding check (`get_utility_model().with_structured_output(Validation)`) → off-topic / refusal / contradiction → `route_after_validator` re-plans (capped at `SUPERVISOR_MAX_TURNS`). Pure model answers skip the check.
- ✅ **Rate limiting** — `memory/short_term.check_rate_limit(redis, user_id, per_min)` (fixed-window INCR/EXPIRE) enforced in `POST /chat` → 429 (`RATE_LIMIT_REQUESTS_PER_MINUTE`, default 60).
- ✅ **Agents** — `greeting` (time-of-day, `stream=True`), `web_search` (Tavily → grounded summary + sources), `task_creator` (`stream=True`, MCP). `app/agents/events.py:emit()` is the shared custom-event helper. `rag`/`calendar` remain stubs.
- ✅ **MCP layer** (§22) — `fastmcp>=3`. `app/mcp/tasks_server.py` = `FastMCP("genie-tasks")` with 8 tools — `create_task` · `list_tasks` · `find_task` · `set_task_status` · `update_task` · `delete_task` · **`summarize_task`** (3-4 line LLM recap of the task's linked chat → its description) · `archive_done_tasks` (each opens its own session → `services/task_service.py`); `app/mcp/client.py` calls them **in-process** (in-memory transport). `uv run python -m app.mcp.tasks_server` serves streamable-HTTP on `TASKS_MCP_HOST:PORT` (8765) for external clients later.
- ✅ **Tasks** — `models/task.py` (`bed5223f2a47`), `task_repo`, `services/task_service.py` (the one code path — REST + MCP + tests; includes `summarize_task` → a 3-4 line LLM recap of the task's chat), `/tasks` REST (`list`, `get`, `create`, `patch` status/details, `{id}/summarize`, `archive-done`, `delete`). `conversation_id` FK `SET NULL`; `create` drops a stale link rather than failing; `task_repo.update` only sets `title` when given (NOT NULL) but sets `description` whenever the key is passed (so it can be cleared).
- ✅ **Conversations**: `GET /conversations` (pinned first, then recency via `conversations.last_message_at`, bumped every message), `GET /conversations/{id}` (clears `unread`; carries `share`), `PATCH /conversations/{id}` (`title` / `project_id` move-or-detach / `pinned` / `unread` — only fields present are touched), `DELETE /conversations/{id}` (cascade + `checkpointer.adelete_thread`), **`{id}/share` GET/POST/DELETE** (public-link control — `conversation_repo.set_share` / `clear_share`, token `secrets.token_urlsafe(16)`, `shared_at` frozen at first share). Auto-title after the first exchange (`services/title_service.py` → `get_utility_model()` / `ainvoke`, so it follows `LLM_PROVIDER`) → persisted + SSE `title` event.
- ✅ **Attachments** (`attachment_service` + `attachment_repo` + `endpoints/attachments.py` + `models/attachment.py`, migration `0b4ae74dbb70`) — `parse_upload` (pure: extension → text; `pypdf` PDF, utf-8 txt/md; 5 MB cap; `AttachmentError` → 422). `create_turn` accepts `attachment_ids`, links rows to the user message, stashes them in the Redis run payload; `_generate` loads the text into `GenieState['attachments']`. `nodes._attachment_note` / `_format_attachments` (§9). One-shot per turn.
- ✅ **Projects** (`models/project.py`, `project_repo.py`, `endpoints/projects.py`) — Claude-style: full CRUD; `conversations.project_id` (`ON DELETE CASCADE`); `POST /chat` takes `project_id` (new chats inherit it); `_generate` loads `project.instructions` fresh each turn → `GenieState.project_instructions` → the supervisor + synthesiser respect them. Chats stay isolated (thread = conversation_id). Knowledge docs = later.
- ⬜ `rag`/`calendar` agents, parallel fan-out, cross-conversation memory (Phase 6 — §15), SQS workers, per-user token quotas

**Frontend** (Next.js 15 · React 19 · Tailwind v3 · `@clerk/nextjs` v7 · npm)
- ✅ **Landing page** at `/` (`components/landing/*`) — voice-AI-concierge positioning, sticky blur nav w/ placeholder links, Framer-Motion hero "live call" animation (`CallOrb`: waveform → spoken request → agent chips → completed actions, loops; static under `prefers-reduced-motion`), logo marquee, how-it-works, features grid, "voice coming soon" band, CTA, 4-col footer. **`/` no longer redirects to `/chat`.**
- ✅ **Light/dark theme** — `next-themes` (`ThemeProvider` outermost in `layout.tsx`, `attribute="class"`, system default); `ThemeToggle` in the nav; global (also themes `/chat`, `/tasks`, Clerk pages). Dark palette = deep violet-black + violet glow.
- ✅ `(app)/` group — `Sidebar`: nav block (**New chat** · **Projects** · **Tasks**, same style) then the **Chats** list (always below every nav item, recency-ordered `useConversations`, active-highlight, hover-to-delete), then `BackendStatus` + Clerk `UserButton` pinned at the bottom.
- ✅ Chat — `/chat` (new) and `/chat/[id]` (a conversation); `ChatView` + `useChat(conversationId?)` is **route-driven** (loads `GET /conversations/{id}` on nav; on the first message of a new chat it POSTs, learns the id, `router.replace('/chat/<id>')`, invalidates the sidebar list; the SSE `title` event refreshes the sidebar). Streams tokens live, input locked mid-turn. Each `Message` has a sender label — "GENIE" brand-gradient + sparkle, or the user's Clerk first name. **Empty state** = a vertically-centred greeting (`GreetingHeadline`: "What can Genie _<two words>_?" — the two words swap every 3.2s with a fade, `prefers-reduced-motion`-safe) above a centred composer; project chats show "New chat in _<name>_" instead.
- ✅ `/tasks` — `TaskBoard`: 3 columns from `useTasks`, **HTML5 drag** a card between columns (`usePatchTask`), **"Archive done"** button (`useArchiveDone`), collapsible **"Archived (N)"**, card → **`TaskModal`** (status, linked chat `/chat/<id>`, editable description, **"Summarise from chat"** = `useSummarizeTask`, delete). `useChat` invalidates `["tasks"]` on `task_created`/`task_updated`/`tasks_archived`. `AgentActivity`/`Message` label `task_summary` → "Summarising the task".
- ✅ **Agent activity** — captions, not a bottom strip. `useChat` handles `agent_start`/`agent_end` → `chatStore.agentStarted/agentEnded` and `message_agents` → `chatStore.setMessageAgents`. `Message` renders an `AgentTrail` **above** the bubble ("🔍 Searching the web" in flight → "🔍 Searched the web" done). `AgentActivity` renders the *unclaimed* active agents as a tail pill (incl. `prompt_enhancer` → "Understanding your request", `task_summary` → "Summarising the task").
- ✅ **Plan strip** (`components/chat/PlanStrip.tsx`) — `useChat` puts the `plan` SSE event into `chatStore.plan`; renders below the project chip bar as numbered steps + a per-step status icon (pending / in_progress / done / failed); cleared on the next send.
- ✅ **Model picker** (`components/chat/ModelPicker.tsx`) — dropdown at the right of the composer footer, just left of the Send button (menu opens upward, `right-0`); `useModels()` (`GET /models`, `staleTime ∞`) + `chatStore.model`. `useChat` seeds it from `conv.model` on load / `localStorage["genie.chat_model"]` for a new chat, and sends it with `postChat`. `chatStore.reset()` keeps `model` so the pick carries across new chats. Hidden when < 2 models. Controls the chat model only. Composer layout: the "Enter to send" hint sits directly under the textarea.
- ✅ **Composer "+" menu** (`components/chat/PlusMenu.tsx`) — footer left slot. **Add files** → hidden `<input accept=".pdf,.txt,.md" multiple>` → `useUploadAttachment` → `chatStore.pendingAttachments` (chips via `AttachmentChips`, shown in the composer; × removes, `useDeleteAttachment`). **Add to project** → submenu (`useProjects` + "Remove from project"): with a conversation → `patchConversation` + `chatStore.setProject`; on a new chat → `chatStore.pendingProjectId` (passed as `project_id` on first send). `useChat.send` collects the `ready` attachment ids + the pending project id. Send is blocked while any upload is in flight. User messages render their file chips (`Message.tsx`).
- ✅ **Post-sign-up gate** — `app/welcome/page.tsx` (client, top-level): after `<SignUp forceRedirectUrl="/welcome">`, polls `getMe()` (`/api/v1/users/me`) every 800 ms (12 s cap) then `router.replace('/chat')` — dodges the Clerk-webhook / `users`-row race (§7.8).
- ✅ **Multi-message turns** — `useChat` tracks a `currentId`; `message_break` finalises the current assistant bubble and starts a new one, `message_agents` tags it. A greeting + answer render as two captioned bubbles, matching the two persisted `messages` rows (with `metadata.agents`) on reload.
- ✅ Zustand `chatStore` (current conversation's messages, `conversationId`, `runId`, `activeAgents`, `model`) / `taskStore`; `lib/api.ts` (`postChat` sends `client_hour` + `model`, `getConversation`, `listConversations`, `deleteConversation`, `chatStreamUrl`, `getHealth`, `listModels`, projects CRUD), `lib/sse.ts` parser matching `core/streaming.py`
- ✅ Clerk: `ClerkProvider` in `<body>` themed via `lib/clerk-appearance.ts` (token-bound, dark-safe); `middleware.ts` = bare `clerkMiddleware()` + `/__clerk/:path*` matcher; `(app)/layout.tsx` gate via `await auth()`; sign-in/up `fallbackRedirectUrl="/chat"`; `clerk doctor` passes
- ✅ **Projects UI** — sidebar "Projects" link; `/projects` grid (`ProjectsIndex` + `NewProjectDialog`); `/projects/[id]` (`ProjectView`: editable name/description, instructions textarea + Save, its chat list, "New chat in this project" → `/chat?project=<id>`, delete). `ChatView` reads `?project`, shows a project chip; project chats get a folder glyph in the sidebar (which still lists **all** chats).
- ⬜ conversation rename/search, per-project default model, project knowledge docs (RAG), image attachments / vision, live optimistic task board (SSE currently just invalidates the query)

**Auth end-to-end**
- ✅ Frontend: real Clerk (dev instance `ins_3Ia08…`, app `app_3Ia08IpcDiBIMwI1FykjqEgLCMm`), keys in `frontend/.env.local`; `useChat` / `lib/api.ts` attach `Authorization: Bearer <getToken()>` on `POST /chat`, the stream fetch, and `GET /conversations/{id}`.
- ✅ Backend verifies the Clerk JWT and owns each conversation with the **real** internal user id. Needs `CLERK_PUBLISHABLE_KEY` (JWKS domain) + `CLERK_SECRET_KEY` (profile/webhook) in `backend/.env`; `CLERK_WEBHOOK_SECRET` for the webhook. Missing/expired token → `401`. With none of these set, the dev-user fallback keeps local work frictionless.

**Infra / local dev**
- ⚠️ The frontend talks to the API at **`http://127.0.0.1:8000`**, not `localhost` — browsers often resolve `localhost` to IPv6 (`::1`) first and a default uvicorn is IPv4-only, which makes the health check spuriously report "offline". `NEXT_PUBLIC_API_URL` + the `lib/api.ts` fallback use `127.0.0.1`; `CORS_ALLOW_ORIGINS` lists both `:3000` hosts.
- ✅ `docker-compose.yml` → Redis (`:6379`) + LocalStack (`:4566`). Postgres/pgvector comes from the **Supabase CLI** stack (`supabase start`, `:54322`); `DATABASE_URL_*` point at the default `postgres` db, Genie's tables live in the **`genie` schema** (visible in Studio).
- ✅ `scripts/setup_supabase.sql` — `CREATE SCHEMA genie` + hybrid-search RPCs (in `genie`, `SET search_path`); indexes/FTS triggers/RLS self-skip until Phase 2 tables exist.
- ⬜ `infrastructure/terraform` (Phase 4), SQS/S3 wiring, CI/CD.

### 19.2 Next up

Phase 1 is complete. Next: **Phase 2 — RAG / Documents** (§15) — the `documents`
/ `document_chunks` migration, the ingestion pipeline + `POST /documents`, and a
registered `rag` agent (`hybrid_search_documents` RPC). Then Phase 3 (Calendar +
async workers) and Phase 6 (memory).

Loose ends worth picking up any time: per-user token quotas enforced in the
supervisor (Phase 5), the real `interrupt_before` confirm flow for calendar
(Phase 3), a `rag`/`calendar`/`prompt_enhancer` skip heuristic for trivially
short turns (the enhancer runs an LLM call on every "hi").

---

## 20. Quick Reference: Key Files Per Feature

| Feature | Primary Files |
|---------|--------------|
| Auth / user verification | `core/clerk.py` (JWT verify) + `api/v1/endpoints/webhooks.py` (sync) |
| User DB record | `db/models/user.py` + `db/repositories/user_repo.py` |
| Clerk JWKS cache tuning | `JWKS_CACHE_TTL_SECONDS` env var (default 3600) |
| Add a new agent | `agents/{name}/agent.py` (`run_{name}`) + an `AgentSpec` in `agents/registry.py` |
| Add a new MCP server | `app/mcp/{name}_server.py` (FastMCP) + a `call_{name}_tool` in `app/mcp/client.py` — see §22 |
| Task board logic | `services/task_service.py` (REST + MCP both call it) · tools `app/mcp/tasks_server.py` |
| Change routing logic | `agents/supervisor/nodes.py:supervisor_node` + `SUPERVISOR_SYSTEM_PROMPT` in `supervisor/prompts.py` (menu auto-built from the registry) |
| Modify hybrid search weights | `agents/rag/retriever.py` → `fts_weight`, `semantic_weight` params |
| Add a new API endpoint | `api/v1/endpoints/{resource}.py` + register in `api/v1/router.py` |
| Add DB table | New SQLAlchemy model in `db/models/` + Alembic migration + repository |
| Change SSE event schema | `core/streaming.py` + `frontend/src/lib/sse.ts` (must stay in sync) |
| Chat share / public view | `conversation_repo` share helpers + `endpoints/conversations.py` `{id}/share` + `endpoints/public.py` (unauth); frontend `ShareChatModal` + `app/share/[token]/` |
| Tune answer formatting | `RESPONSE_FORMAT_GUIDE` in `agents/supervisor/prompts.py` (the synthesiser/drafter spec) |
| Code-block colours / a highlighted language | `globals.css` `.hljs-*` rules + `--hl-*` / `--code-*` vars; languages come from `rehype-highlight`'s common set automatically |
| Business-doc draft card | `DOCUMENT_BLOCK_GUIDE` in `agents/supervisor/prompts.py` (when/how the model emits ```` ```document ````) + `components/chat/DocumentCard.tsx` (render + Copy) |
| Regenerate / retry / edit a turn | `chat_service.regenerate_turn` (`adelete_thread` + replay `messages` rows) · `POST /chat/{id}/regenerate` · frontend `useChat.regenerate` + `MessageActions` |
| Message 👍/👎 | `message_repo.set_feedback` (→ `messages.metadata.feedback`) + `core/observability.send_run_feedback` (LangSmith) · `POST /messages/{id}/feedback` |
| Update memory consolidation | `workers/memory_consolidation.py` + `memory/long_term.py` |
| Tune token budget | `MAX_TOKENS_PER_RUN` env var + check in `supervisor/nodes.py` |
| Switch LLM provider | `LLM_PROVIDER=openai\|groq` env var — the fallback chat model + the fixed utility model (embeddings stay OpenAI) |
| Add a model to the picker | `MODEL_CATALOG` in `agents/models.py` (one `ModelSpec` row) — no other change; `GET /models` filters by which provider keys are set |
| Support a new attachment file type | `attachment_service._KINDS` + a parse branch in `parse_upload` |
| Support a new KB file type | `document_service._KIND` + `Document.DOCUMENT_KINDS` + a branch in `partition_service.partition` |
| Tune project retrieval | `projects.rag_settings` (via `PATCH /projects/{id}`) — `schemas/rag.py:RagSettings` |
| Add an ingestion pipeline phase | `Document.DOCUMENT_PHASES` + a step in `ingestion_worker.ingest_document` + a `_publish` |
| Add logging / redaction rule | `core/logging.py` (`redact_processor`, `_SECRET_KEYS`, `preview`) — see §21 |

---

## 21. Observability & Logging

> **Datadog is the destination.** The Datadog agent will ship container stdout;
> until it's wired, logs render to console (dev) / JSON (prod). Nothing about how
> we log changes when Datadog lands — it just reads what's already emitted.

### 21.1 The rule — log every step

**Every module logs what flows through it.** When you write or change a feature,
add `structlog` lines at each meaningful step — not one log per function, but one
per *decision, external call, state transition, and error*. A reader should be
able to reconstruct a request from the logs alone.

- Get a logger per module: `logger = structlog.get_logger(__name__)`.
- Structured only — `logger.info("event_name", key=value, …)`, never f-strings.
  Event names are `snake_case`, past/near-tense, greppable
  (`chat_turn_accepted`, `agent_run_done`, `web_search_results`).
- **Levels**: `debug` = fine-grained trace (per-token, cache hits, model build);
  `info` = the milestones of a request (accepted, planned, agent done, persisted,
  completed); `warning` = handled-but-notable (fallback used, plan step dropped,
  404, replan); `error` / `logger.exception(...)` = unhandled or config-broken.
  Dev shows `debug`+, prod shows `info`+.
- **Reference the variables that matter**: ids (`user_id`, `conversation_id`,
  `run_id`, `task_id`), counts (`chars`, `tokens`, `sources`, `count`),
  durations (`duration_ms`), decisions (`agent`, `status`, `via`, `reason`).
- **Never log** raw user message bodies, full documents, or model outputs —
  use `preview(text, limit=160)` from `core/logging.py` for a short single-line
  excerpt, or just log `chars=len(text)`.
- **Secrets are auto-scrubbed** but don't rely on it as a licence to log them:
  `core/logging.py:redact_processor` runs on *every* event and masks any field
  whose name is a known secret (`token`, `password`, `api_key`, `authorization`,
  `*_secret`, `database_url`, `redis_url`, …) or whose value looks like a JWT /
  `sk_…` / `Bearer …` / a URL with inline credentials. `total_tokens`,
  `token_budget`, `token_usage` etc. are counts and pass through untouched. Add
  new sensitive field names to `_SECRET_KEYS` / `_SECRET_SUFFIXES`.

### 21.2 What already logs

- **HTTP** — `core/middleware.py`: `request_started` / `request_completed`
  (method, status, `duration_ms`, client) with a bound `request_id` +
  `path` on every downstream log (`/health*` is silenced).
- **Auth** — `core/clerk.py`: JWKS cache hit/fetch, token verified/expired/
  invalid, `clerk_user_resolved` (`via` = redis_cache | db | autoprovision),
  dev-user use. `core/clerk_api.py`: Backend-API fetch.
- **Chat flow** — `services/chat_service.py`: `chat_create_turn_start` →
  `chat_turn_accepted` → `chat_stream_start` → `chat_project_instructions_loaded`
  → `chat_graph_invoke` → per-event (`chat_agent_start/end`, `chat_plan`,
  `chat_segment`, `chat_model_call_done`) → `chat_graph_done` →
  `message_persisted` (×N) → `chat_turn_completed`.
- **Agent graph** — `agents/supervisor/nodes.py`: `supervisor_start` /
  `supervisor_planned` (steps + rationale), `executor_start`, `agent_run_start` /
  `agent_run_done` (`duration_ms`, sources) / `agent_run_failed`,
  `synthesiser_compose` / `synthesiser_done`, `validator_verdict`,
  `validator_replan`. `greeting` / `web_search` / `tavily_search` /
  `task_creator` (`task_creator_parsed`, per-op) log their own steps;
  `agents/models.py` logs every model build.
- **MCP / tasks** — `app/mcp/client.py`: `mcp_tool_call` / `mcp_tool_result`;
  each tool + `task_service` + `task_repo` log their ops; `chat_service` logs the
  forwarded `chat_task_created` / `chat_task_updated` / `chat_tasks_archived`.
- **DB** — `db/repositories/base.py`: `db_insert` on every write;
  `db_get_by_id` / `*_listed` at debug. Each repo logs its mutations
  (`conversation_created`, `message_persisted`, `project_updated`, `user_*`).
  `db/session.py`: engine init (URL scrubbed), `db_session_rollback`.
- **Message actions** — `chat_service`: `chat_regenerate_accepted`,
  `chat_regenerate_seed`; `message_repo`: `messages_truncated`, `message_edited`,
  `message_feedback_set`; `core/observability`: `message_feedback_langsmith`.
- **Chat share** — `conversation_repo`: `conversation_shared` / `conversation_unshared`
  (only `token_prefix`, never the full capability token); `endpoints/conversations.py`:
  `conversation_share_enabled` / `_disabled`, `share_token_collision`;
  `endpoints/public.py`: `shared_view_served` (`token_prefix`, `message_count`, `ip`).
- **Startup** — `main.py`: `startup_begin` (which integrations are configured),
  `agent_registry_loaded`, `redis_connected`, `database_connected`,
  `checkpointer_ready`, `startup_complete`; `configure_tracing()` logs LangSmith
  on/off.
- Third-party noise (`httpx`, `httpcore`, `openai`, `groq`, `sqlalchemy.engine`, …)
  is pinned to WARNING in `core/logging.py:_NOISY_LOGGERS`.

### 21.3 Still to wire

Datadog agent + `ddtrace` (APM), log-based metrics/monitors, trace-id
correlation with LangSmith, and structured logging in the Phase 2/3 stubs
(`workers/*`, `memory/*`, `services/document_service.py`) as they are built.
The MCP layer (§22) already logs each tool call in/out.

---

## 22. MCP Layer

> Genie exposes some capabilities as **MCP** (Model Context Protocol) tool
> servers built with **FastMCP** (`fastmcp>=3`, `requirements.txt` §3). Agents
> call them; external MCP clients (Claude Desktop, …) can too, later.

### 22.1 Shape

```
app/mcp/
├── __init__.py
├── tasks_server.py   ← FastMCP("genie-tasks") — task-board CRUD as @mcp.tool funcs
└── client.py         ← call_tasks_tool(name, args) — in-process, in-memory transport
```

- **In-process (now)** — `app/mcp/client.py` does `async with Client(<server>)`
  which uses FastMCP's **in-memory** transport: same process, no socket, no
  subprocess. The `task_creator` agent calls `call_tasks_tool(...)`.
- **Standalone (later)** — `uv run python -m app.mcp.tasks_server` serves the same
  `mcp` object over **streamable-HTTP** on `TASKS_MCP_HOST:TASKS_MCP_PORT`
  (default `127.0.0.1:8765`) for external MCP clients. No auth on that transport
  yet — out of scope.

### 22.2 Rules

- **Stateless tools.** Every tool takes the ids it needs as explicit args
  (`user_id` always — the agent passes `GenieState['user_id']`). Each tool opens
  its own DB session (`get_sessionmaker()()`) and delegates to a **service**
  (`app/services/task_service.py`) — never the repo directly, never business
  logic in the tool body.
- **Log every call** — `client.py` logs `mcp_tool_call` / `mcp_tool_result`;
  each tool logs its own `mcp_*` line (§21).
- Return plain JSON-able dicts (`task_service.to_dict`).

### 22.3 Add a new MCP server

1. `app/mcp/<name>_server.py` — `mcp = FastMCP("genie-<name>", instructions=…)`,
   `@mcp.tool` async funcs → a service, plus a `main()` / `__main__` entrypoint.
2. `app/mcp/client.py` — a `call_<name>_tool(...)` helper (or generalise).
3. Tests in `tests/mcp/` — `async with Client(mcp)` with the service faked.
