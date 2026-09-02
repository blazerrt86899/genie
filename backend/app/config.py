"""Application settings — loaded from environment / .env (CLAUDE.md §6).

Access via ``get_settings()`` (cached). Never read ``os.environ`` directly
elsewhere.
"""

from __future__ import annotations

import base64
import binascii
from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _domain_from_publishable_key(pk: str | None) -> str | None:
    """`pk_test_<base64>` / `pk_live_<base64>` decodes to `<frontend-api-host>$`."""
    if not pk or not pk.startswith(("pk_test_", "pk_live_")):
        return None
    encoded = pk.split("_", 2)[2]
    try:
        decoded = base64.b64decode(encoded + "==").decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return None
    return decoded.rstrip("$") or None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # ─── App ────────────────────────────────────────────────────────────────
    APP_ENV: Literal["development", "staging", "production"] = "development"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    CORS_ALLOW_ORIGINS: str = "http://localhost:3000"
    # Absolute base of the Next.js app — used to build public share URLs
    # (`{FRONTEND_BASE_URL}/share/{token}`). No trailing slash.
    FRONTEND_BASE_URL: str = "http://localhost:3000"

    # ─── Clerk ──────────────────────────────────────────────────────────────
    CLERK_SECRET_KEY: str | None = None
    CLERK_PUBLISHABLE_KEY: str | None = None
    CLERK_WEBHOOK_SECRET: str | None = None
    CLERK_DOMAIN: str | None = None

    # ─── Database (three modes — CLAUDE.md §3) ──────────────────────────────
    DATABASE_URL_DIRECT: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/genie"
    DATABASE_URL_POOL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/genie"
    DATABASE_URL_SESSION: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/genie"
    SUPABASE_URL: str | None = None
    SUPABASE_ANON_KEY: str | None = None
    SUPABASE_SERVICE_ROLE_KEY: str | None = None

    # ─── Redis ──────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    JWKS_CACHE_TTL_SECONDS: int = 3600
    CLERK_USER_CACHE_TTL_SECONDS: int = 300

    # ─── LLM (optional at boot) ────────────────────────────────────────────
    # LLM_PROVIDER picks which chat backend the agent graph uses. "groq" is for
    # local / testing (OpenAI-credit-free); embeddings always stay on OpenAI.
    LLM_PROVIDER: Literal["openai", "groq"] = "openai"

    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    # Required only when ANTHROPIC_API_KEY is an identity-linked key (the API
    # returns "anthropic-workspace-id is required" without it). Sent as a header.
    ANTHROPIC_WORKSPACE_ID: str | None = None
    OPENAI_CHAT_MODEL: str = "gpt-4o-2024-08-06"
    OPENAI_TITLE_MODEL: str = "gpt-4o-mini"  # cheap model for conversation titles
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"

    GROQ_API_KEY: str | None = None
    GROQ_CHAT_MODEL: str = "openai/gpt-oss-120b"
    # cheap/fast Groq model: enhancer, greeting, titles, validator
    GROQ_UTILITY_MODEL: str = "qwen/qwen3.8-27b"

    # ─── LangSmith ─────────────────────────────────────────────────────────
    # Accept both the current LANGSMITH_* names and the legacy LANGCHAIN_* ones.
    LANGSMITH_TRACING: bool = Field(
        default=False,
        validation_alias=AliasChoices("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2"),
    )
    LANGSMITH_ENDPOINT: str = Field(
        default="https://api.smith.langchain.com",
        validation_alias=AliasChoices("LANGSMITH_ENDPOINT", "LANGCHAIN_ENDPOINT"),
    )
    LANGSMITH_API_KEY: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LANGSMITH_API_KEY", "LANGCHAIN_API_KEY"),
    )
    LANGSMITH_PROJECT: str = Field(
        default="genie-dev",
        validation_alias=AliasChoices("LANGSMITH_PROJECT", "LANGCHAIN_PROJECT"),
    )

    # ─── Search ────────────────────────────────────────────────────────────
    TAVILY_API_KEY: str | None = None

    # ─── MCP (CLAUDE.md §22) — only used when a server runs standalone ──────
    TASKS_MCP_HOST: str = "127.0.0.1"
    TASKS_MCP_PORT: int = 8765

    # ─── Google OAuth (Phase 3) ────────────────────────────────────────────
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    OAUTH_TOKEN_ENCRYPTION_KEY: str | None = None

    # ─── AWS ───────────────────────────────────────────────────────────────
    AWS_REGION: str = "ap-south-1"
    AWS_ENDPOINT_URL: str | None = None  # set → LocalStack; unset → real AWS
    SQS_QUEUE_URL: str | None = None
    S3_BUCKET_NAME: str | None = None
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None

    # ─── Knowledge Base / RAG ingestion ────────────────────────────────────
    RUN_INGESTION_WORKER: bool | None = None  # None → not is_production
    INGESTION_CONCURRENCY: int = 3
    DOCUMENT_MAX_MB: int = 25

    # ─── Limits ────────────────────────────────────────────────────────────
    MAX_TOKENS_PER_RUN: int = 50000
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 60
    SUPERVISOR_MAX_TURNS: int = 2  # how many times the supervisor may (re)plan per run

    # ─── Guardrails (input/output PII + secret scanning) ───────────────────
    GUARDRAILS_ENABLED: bool = True
    GUARDRAIL_INPUT_ENABLED: bool = True
    GUARDRAIL_OUTPUT_ENABLED: bool = True

    # ─── Semantic response cache (pgvector) ────────────────────────────────
    RESPONSE_CACHE_ENABLED: bool = True
    RESPONSE_CACHE_TTL_HOURS: int = 24
    RESPONSE_CACHE_SIMILARITY: float = 0.93  # cosine floor for a cache hit
    RESPONSE_CACHE_MAX_PER_USER: int = 200

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ALLOW_ORIGINS.split(",") if o.strip()]

    @property
    def clerk_domain(self) -> str | None:
        """Clerk Frontend API host — for the JWKS endpoint.
        Explicit ``CLERK_DOMAIN`` wins; otherwise derived from the publishable key."""
        return self.CLERK_DOMAIN or _domain_from_publishable_key(self.CLERK_PUBLISHABLE_KEY)

    @property
    def clerk_configured(self) -> bool:
        """True once the backend can verify Clerk JWTs (has a JWKS domain)."""
        return bool(self.clerk_domain)

    @property
    def clerk_backend_api_enabled(self) -> bool:
        """True when the Clerk Backend API can be called (profile enrichment, webhook)."""
        return bool(self.CLERK_SECRET_KEY)

    @property
    def llm_configured(self) -> bool:
        """True once the active provider (LLM_PROVIDER) has an API key."""
        if self.LLM_PROVIDER == "groq":
            return bool(self.GROQ_API_KEY)
        return bool(self.OPENAI_API_KEY)

    @property
    def chat_model_name(self) -> str:
        return self.GROQ_CHAT_MODEL if self.LLM_PROVIDER == "groq" else self.OPENAI_CHAT_MODEL

    @property
    def utility_model_name(self) -> str:
        return (
            self.GROQ_UTILITY_MODEL if self.LLM_PROVIDER == "groq" else self.OPENAI_TITLE_MODEL
        )

    @property
    def tavily_configured(self) -> bool:
        return bool(self.TAVILY_API_KEY)

    @property
    def langsmith_enabled(self) -> bool:
        return bool(self.LANGSMITH_TRACING and self.LANGSMITH_API_KEY)

    @property
    def aws_configured(self) -> bool:
        """True once S3 + SQS targets exist (LocalStack or real AWS)."""
        return bool(self.S3_BUCKET_NAME and self.SQS_QUEUE_URL)

    @property
    def run_ingestion_worker(self) -> bool:
        if self.RUN_INGESTION_WORKER is not None:
            return self.RUN_INGESTION_WORKER
        return not self.is_production  # prod runs it as a separate ECS service


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
