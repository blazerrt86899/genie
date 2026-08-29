"""Declarative base + shared column mixins.

All Genie tables live in the dedicated ``genie`` Postgres schema (not ``public``)
so the local Supabase stack shares one database with other projects and Supabase
Studio shows them under its schema switcher. See ``scripts/setup_supabase.sql``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DB_SCHEMA = "genie"


class Base(DeclarativeBase):
    metadata = MetaData(schema=DB_SCHEMA)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
