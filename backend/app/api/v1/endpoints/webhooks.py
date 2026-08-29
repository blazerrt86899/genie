"""Clerk webhook — user lifecycle sync (CLAUDE.md §7.4). STUB (Phase 1).

No auth — Svix signature is verified inside the handler. Never process an
unsigned webhook.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/clerk", status_code=200)
async def clerk_webhook(request: Request) -> dict:
    # Phase 1:
    #   1. wh = Webhook(settings.CLERK_WEBHOOK_SECRET); event = wh.verify(body, svix_headers)
    #   2. dispatch user.created / user.updated / user.deleted -> UserRepository
    raise HTTPException(status_code=501, detail="Clerk webhook handler not implemented yet")
