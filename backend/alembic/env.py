"""Alembic environment — async, driven by app settings (CLAUDE.md §3).

Uses DATABASE_URL_DIRECT. Manages app tables only.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from app.config import settings
from app.db.models import Base  # noqa: F401  (imports all active models)
from app.db.models.base import DB_SCHEMA
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.DATABASE_URL_DIRECT)

target_metadata = Base.metadata


# The LangGraph checkpointer creates these in the genie schema itself
# (checkpointer.setup()) — never Alembic-managed (CLAUDE.md §8.2).
_CHECKPOINTER_TABLES = {
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
    "checkpoint_migrations",
}


def _include_name(name, type_, parent_names):  # noqa: ARG001
    """Only ever look at the genie schema, and never at the checkpointer tables."""
    if type_ == "schema":
        return name == DB_SCHEMA
    if type_ == "table":
        return name not in _CHECKPOINTER_TABLES
    return True


def _include_object(obj, name, type_, reflected, compare_to):  # noqa: ARG001
    if type_ == "table" and name in _CHECKPOINTER_TABLES:
        return False
    return True


_CONFIGURE = dict(
    target_metadata=target_metadata,
    compare_type=True,
    version_table_schema=DB_SCHEMA,  # keep alembic_version inside the genie schema
    include_schemas=True,
    include_name=_include_name,
    include_object=_include_object,
)


def run_migrations_offline() -> None:
    context.configure(
        url=settings.DATABASE_URL_DIRECT,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_CONFIGURE,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    # Commit the schema immediately: alembic's begin_transaction() won't manage a
    # transaction that's already open, so the migration would never be committed.
    connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {DB_SCHEMA}"))
    connection.commit()
    context.configure(connection=connection, **_CONFIGURE)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
