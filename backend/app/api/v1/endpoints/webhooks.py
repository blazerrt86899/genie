"""Clerk webhook — keeps the `users` table in sync (CLAUDE.md §7.4).

No auth — the Svix signature is verified inside the handler. An unsigned or
badly-signed payload is never processed.

Local testing (no public URL needed):
    clerk webhooks --forward-to localhost:8000/api/v1/webhooks/clerk
"""

from __future__ import annotations

import json

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from svix.webhooks import Webhook, WebhookVerificationError

from app.config import settings
from app.db.repositories.user_repo import UserRepository
from app.db.session import get_db

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/clerk", status_code=200)
async def clerk_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    if not settings.CLERK_WEBHOOK_SECRET:
        raise HTTPException(status_code=501, detail="CLERK_WEBHOOK_SECRET not configured")

    payload = await request.body()
    headers = {
        "svix-id": request.headers.get("svix-id", ""),
        "svix-timestamp": request.headers.get("svix-timestamp", ""),
        "svix-signature": request.headers.get("svix-signature", ""),
    }
    try:
        # svix.verify() only checks the signature (json_parse=False); a malformed
        # signature raises ValueError (binascii), a wrong one WebhookVerificationError.
        Webhook(settings.CLERK_WEBHOOK_SECRET).verify(payload, headers)
    except (WebhookVerificationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook signature") from exc

    event = json.loads(payload)
    event_type: str = event.get("type", "")
    data: dict = event.get("data") or {}
    repo = UserRepository(db)

    if event_type == "user.created":
        await repo.create_from_clerk(data)
    elif event_type == "user.updated":
        await repo.update_from_clerk(data)
    elif event_type == "user.deleted":
        await repo.soft_delete_by_clerk_id(data["id"])
    else:
        logger.info("clerk_webhook_ignored", event_type=event_type)

    return {"received": True}
