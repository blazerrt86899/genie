"""Model catalog endpoint — powers the composer's model picker (CLAUDE.md §9, §14).

Lists the chat models we have a provider key for; the client stores the chosen
``id`` per conversation and sends it back on ``POST /chat``.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.agents.models import available_models, default_model_id
from app.core.clerk import get_current_user
from app.db.models.user import User

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/models", tags=["models"])


class ModelOption(BaseModel):
    id: str
    label: str
    provider: str
    hint: str


class ModelsResponse(BaseModel):
    models: list[ModelOption]
    default: str | None  # catalog id the UI selects when a chat has none


@router.get("", response_model=ModelsResponse)
async def list_models(user: User = Depends(get_current_user)) -> ModelsResponse:
    specs = available_models()
    logger.info("models_listed", user_id=str(user.id), count=len(specs))
    return ModelsResponse(
        models=[
            ModelOption(id=s.id, label=s.label, provider=s.provider, hint=s.hint)
            for s in specs
        ],
        default=default_model_id(),
    )
