"""Thin Clerk Backend API client — used to enrich a user we auto-provision from
a session token (which carries no email/name) and by the webhook handler.

Needs ``CLERK_SECRET_KEY``. All helpers degrade to ``None`` when it's absent or
the call fails — provisioning then falls back to a placeholder email.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)

_BASE = "https://api.clerk.com/v1"


async def fetch_clerk_user(clerk_id: str) -> dict[str, Any] | None:
    if not settings.clerk_backend_api_enabled:
        return None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{_BASE}/users/{clerk_id}",
                headers={"Authorization": f"Bearer {settings.CLERK_SECRET_KEY}"},
            )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        logger.warning("clerk_user_fetch_failed", clerk_id=clerk_id, error=str(exc))
        return None


def primary_email(clerk_user: dict[str, Any]) -> str | None:
    """Works for both Backend-API user objects and webhook ``data`` payloads."""
    emails = clerk_user.get("email_addresses") or []
    if not emails:
        return None
    primary_id = clerk_user.get("primary_email_address_id")
    chosen = next((e for e in emails if e.get("id") == primary_id), emails[0])
    return chosen.get("email_address")


def full_name(clerk_user: dict[str, Any]) -> str | None:
    name = f"{clerk_user.get('first_name') or ''} {clerk_user.get('last_name') or ''}".strip()
    return name or None


def avatar_url(clerk_user: dict[str, Any]) -> str | None:
    return clerk_user.get("image_url")


def email_verified(clerk_user: dict[str, Any]) -> bool:
    emails = clerk_user.get("email_addresses") or []
    primary_id = clerk_user.get("primary_email_address_id")
    chosen = next((e for e in emails if e.get("id") == primary_id), emails[0] if emails else {})
    return (chosen.get("verification") or {}).get("status") == "verified"
