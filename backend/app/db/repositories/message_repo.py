"""MessageRepository (CLAUDE.md §4.4). All queries filter by user_id."""

from __future__ import annotations

import uuid
from datetime import datetime

import structlog
from sqlalchemy import delete, func, select, update

from app.core.logging import preview
from app.db.models.message import Message
from app.db.repositories.base import BaseRepository

logger = structlog.get_logger(__name__)


class MessageRepository(BaseRepository[Message]):
    model = Message

    async def add_message(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        role: str,
        content: str,
        metadata: dict | None = None,
        created_at: datetime | None = None,
    ) -> Message:
        # ``created_at`` is normally the DB default (transaction ``now()``), which
        # is identical for every row in one commit — pass an explicit value to
        # keep several assistant messages from one turn in order.
        msg = Message(
            conversation_id=conversation_id,
            user_id=user_id,
            role=role,
            content=content,
            message_metadata=metadata or {},
        )
        if created_at is not None:
            msg.created_at = created_at
        saved = await self.add(msg)
        logger.info(
            "message_persisted",
            conversation_id=str(conversation_id),
            role=role,
            chars=len(content),
            preview=preview(content, 120),
            metadata_keys=sorted((metadata or {}).keys()) or None,
        )
        return saved

    async def get_for_user(
        self, message_id: uuid.UUID, user_id: uuid.UUID
    ) -> Message | None:
        result = await self.db.execute(
            select(Message).where(
                Message.id == message_id, Message.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def delete_after(
        self, conversation_id: uuid.UUID, after: datetime, *, inclusive: bool = False
    ) -> int:
        """Delete every message in the conversation created at/after ``after``.

        Used by regenerate / retry / edit to truncate the tail before replaying.
        """
        col = Message.created_at
        cond = col >= after if inclusive else col > after
        result = await self.db.execute(
            delete(Message).where(Message.conversation_id == conversation_id, cond)
        )
        await self.db.commit()
        count = getattr(result, "rowcount", 0) or 0
        logger.info(
            "messages_truncated",
            conversation_id=str(conversation_id),
            deleted=count,
            inclusive=inclusive,
        )
        return count

    async def set_content(
        self, message_id: uuid.UUID, user_id: uuid.UUID, content: str
    ) -> None:
        await self.db.execute(
            update(Message)
            .where(Message.id == message_id, Message.user_id == user_id)
            .values(content=content)
        )
        await self.db.commit()
        logger.info("message_edited", message_id=str(message_id), chars=len(content))

    async def set_feedback(
        self, message_id: uuid.UUID, user_id: uuid.UUID, vote: str | None
    ) -> Message | None:
        msg = await self.get_for_user(message_id, user_id)
        if msg is None:
            return None
        meta = dict(msg.message_metadata or {})
        if vote:
            meta["feedback"] = vote
        else:
            meta.pop("feedback", None)
        await self.db.execute(
            update(Message)
            .where(Message.id == message_id, Message.user_id == user_id)
            .values(message_metadata=meta)
        )
        await self.db.commit()
        logger.info("message_feedback_set", message_id=str(message_id), vote=vote)
        msg.message_metadata = meta
        return msg

    async def list_for_conversation(
        self, conversation_id: uuid.UUID, limit: int = 200
    ) -> list[Message]:
        result = await self.db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
            .limit(limit)
        )
        rows = list(result.scalars().all())
        logger.debug(
            "messages_loaded", conversation_id=str(conversation_id), count=len(rows)
        )
        return rows

    async def usage_totals(
        self, user_id: uuid.UUID, since: datetime | None = None
    ) -> dict:
        """Usage for the Settings → Usage panel: summed reply tokens + message
        count. Uses the persisted `metadata.total_tokens` where present, else a
        ``chars / 4`` estimate so pre-tracking chats aren't shown as 0.
        ``since=None`` → all time."""
        per_msg = func.coalesce(
            Message.message_metadata["total_tokens"].as_integer(),
            func.char_length(Message.content) / 4,
        )
        tok_q = select(func.coalesce(func.sum(per_msg), 0)).where(
            Message.user_id == user_id, Message.role == "assistant"
        )
        msg_q = (
            select(func.count()).select_from(Message).where(Message.user_id == user_id)
        )
        if since is not None:
            tok_q = tok_q.where(Message.created_at >= since)
            msg_q = msg_q.where(Message.created_at >= since)
        tokens = await self.db.scalar(tok_q)
        messages = await self.db.scalar(msg_q)
        return {"tokens": int(tokens or 0), "messages": int(messages or 0)}

    async def token_usage_windows(
        self, user_id: uuid.UUID, day_start: datetime, week_start: datetime
    ) -> dict:
        """Estimated reply tokens in three windows, in one query."""
        per_msg = func.coalesce(
            Message.message_metadata["total_tokens"].as_integer(),
            func.char_length(Message.content) / 4,
        )
        row = (
            await self.db.execute(
                select(
                    func.coalesce(func.sum(per_msg), 0),
                    func.coalesce(
                        func.sum(per_msg).filter(Message.created_at >= day_start), 0
                    ),
                    func.coalesce(
                        func.sum(per_msg).filter(Message.created_at >= week_start), 0
                    ),
                ).where(Message.user_id == user_id, Message.role == "assistant")
            )
        ).one()
        return {
            "all_time": int(row[0] or 0),
            "daily": int(row[1] or 0),
            "weekly": int(row[2] or 0),
        }
