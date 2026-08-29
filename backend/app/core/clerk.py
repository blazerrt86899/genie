"""Clerk auth: JWKS verification + ``get_current_user`` dependency (CLAUDE.md §7).

The backend NEVER mints JWTs — it only verifies Clerk's. In development, when
``CLERK_SECRET_KEY`` / ``CLERK_DOMAIN`` are unset, a fixed dev user is returned
so protected routes are usable without a Clerk application.

Full JWKS verification + Redis JWKS cache + clerk_id->user_id resolution land in
Phase 1 (CLAUDE.md §7.3). This module currently implements only the dev path.
"""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models.user import User
from app.db.session import get_db

security_scheme = HTTPBearer(auto_error=False)

DEV_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
DEV_CLERK_ID = "user_dev_local"


def _dev_user() -> User:
    return User(
        id=DEV_USER_ID,
        clerk_id=DEV_CLERK_ID,
        email="dev@genie.local",
        full_name="Local Dev",
        email_verified=True,
        token_budget=1_000_000,
        user_metadata={},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not settings.clerk_configured:
        if settings.is_production:
            raise HTTPException(status_code=500, detail="Clerk is not configured")
        return _dev_user()

    # ─── Phase 1: real verification ───────────────────────────────────────
    #   1. fetch + cache JWKS (Redis, TTL JWKS_CACHE_TTL_SECONDS)
    #   2. jwt.decode(token, jwks, algorithms=["RS256"], verify_aud=False)
    #   3. resolve payload["sub"] -> internal user (Redis cache -> UserRepository)
    #   4. auto-create via create_from_clerk_token if webhook hasn't arrived
    raise HTTPException(status_code=501, detail="Clerk JWT verification not implemented yet")
