"""Clerk auth: JWKS-verified session JWT → internal user (CLAUDE.md §7.3).

The backend NEVER mints JWTs — it only verifies Clerk's. When no Clerk domain is
configured (`settings.clerk_configured` is False) a fixed dev user is returned so
local work needs no Clerk app; otherwise every request must carry a valid
`Authorization: Bearer <clerk session token>`.
"""

from __future__ import annotations

import json
import uuid

import httpx
import jwt
import structlog
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.redis import get_redis
from app.db.models.user import User
from app.db.repositories.user_repo import UserRepository
from app.db.session import get_db

logger = structlog.get_logger(__name__)
security_scheme = HTTPBearer(auto_error=False)

DEV_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
DEV_CLERK_ID = "user_dev_local"

_JWKS_KEY = "clerk:jwks"
_USER_CACHE_KEY = "user_by_clerk:{clerk_id}"


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


async def _fetch_jwks() -> dict:
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(f"https://{settings.clerk_domain}/.well-known/jwks.json")
    resp.raise_for_status()
    return resp.json()


async def _get_jwks(redis: Redis, *, force_refresh: bool = False) -> dict:
    """Clerk's public JWKS, cached in Redis for ``JWKS_CACHE_TTL_SECONDS``."""
    if not force_refresh:
        cached = await redis.get(_JWKS_KEY)
        if cached:
            logger.debug("clerk_jwks_cache_hit", key=_JWKS_KEY)
            return json.loads(cached)
    logger.info(
        "clerk_jwks_fetching", domain=settings.clerk_domain, force_refresh=force_refresh
    )
    jwks = await _fetch_jwks()
    await redis.setex(_JWKS_KEY, settings.JWKS_CACHE_TTL_SECONDS, json.dumps(jwks))
    logger.info(
        "clerk_jwks_cached", keys=len(jwks.get("keys", [])), ttl_s=settings.JWKS_CACHE_TTL_SECONDS
    )
    return jwks


def _decode(token: str, jwks: dict) -> dict:
    kid = jwt.get_unverified_header(token).get("kid")
    jwk_set = jwt.PyJWKSet.from_dict(jwks)
    signing_key = next((k for k in jwk_set.keys if k.key_id == kid), None)
    if signing_key is None:
        raise KeyError(kid)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        options={"verify_aud": False},  # Clerk omits `aud` by default
    )


async def _verify_token(token: str, redis: Redis) -> dict:
    jwks = await _get_jwks(redis)
    try:
        return _decode(token, jwks)
    except KeyError:
        # kid rotated — refresh the JWKS once and retry.
        return _decode(token, await _get_jwks(redis, force_refresh=True))


async def _resolve_user(payload: dict, db: AsyncSession, redis: Redis) -> User:
    clerk_id = payload.get("sub")
    if not clerk_id:
        logger.warning("clerk_token_missing_sub", claims=sorted(payload.keys()))
        raise HTTPException(status_code=401, detail="Missing subject claim")

    repo = UserRepository(db)
    cache_key = _USER_CACHE_KEY.format(clerk_id=clerk_id)

    cached_id = await redis.get(cache_key)
    user = await repo.get_by_id(uuid.UUID(str(cached_id))) if cached_id else None
    resolved_via = "redis_cache" if user else None
    if user is None:
        user = await repo.get_by_clerk_id(clerk_id)
        resolved_via = "db" if user else None
    if user is None:
        logger.info("clerk_user_autoprovision_start", clerk_id=clerk_id)
        user = await repo.create_from_clerk_token(payload)
        resolved_via = "autoprovision"

    await redis.setex(cache_key, settings.CLERK_USER_CACHE_TTL_SECONDS, str(user.id))
    await repo.touch_last_active(user.id)
    logger.info(
        "clerk_user_resolved",
        clerk_id=clerk_id,
        user_id=str(user.id),
        via=resolved_via,
    )
    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> User:
    if not settings.clerk_configured:
        if settings.is_production:
            logger.error("clerk_not_configured_in_production")
            raise HTTPException(status_code=500, detail="Clerk is not configured")
        logger.debug("clerk_dev_user_used", user_id=str(DEV_USER_ID))
        return _dev_user()

    if credentials is None:
        logger.info("clerk_auth_missing_bearer")
        raise HTTPException(status_code=401, detail="Missing bearer token")

    try:
        payload = await _verify_token(credentials.credentials, redis)
    except jwt.ExpiredSignatureError as exc:
        logger.info("clerk_token_expired")
        raise HTTPException(status_code=401, detail="Token expired") from exc
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        logger.info("clerk_token_invalid", error=str(exc))
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    logger.debug("clerk_token_verified", sub=payload.get("sub"))
    return await _resolve_user(payload, db, redis)
