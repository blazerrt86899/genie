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
    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    OPENAI_CHAT_MODEL: str = "gpt-4o-2024-08-06"
    OPENAI_TITLE_MODEL: str = "gpt-4o-mini"  # cheap model for conversation titles
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"

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

    # ─── Google OAuth (Phase 3) ────────────────────────────────────────────
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    OAUTH_TOKEN_ENCRYPTION_KEY: str | None = None

    # ─── AWS ───────────────────────────────────────────────────────────────
    AWS_REGION: str = "ap-south-1"
    AWS_ENDPOINT_URL: str | None = None
    SQS_QUEUE_URL: str | None = None
    S3_BUCKET_NAME: str | None = None
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None

    # ─── Limits ────────────────────────────────────────────────────────────
    MAX_TOKENS_PER_RUN: int = 50000
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 60
    SUPERVISOR_MAX_TURNS: int = 2  # how many times the supervisor may (re)plan per run

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
        return bool(self.OPENAI_API_KEY)

    @property
    def tavily_configured(self) -> bool:
        return bool(self.TAVILY_API_KEY)

    @property
    def langsmith_enabled(self) -> bool:
        return bool(self.LANGSMITH_TRACING and self.LANGSMITH_API_KEY)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
