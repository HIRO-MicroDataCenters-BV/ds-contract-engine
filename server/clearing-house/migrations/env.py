"""Alembic environment.

Two departures from the generated default, both deliberate:

1. The database URL comes from application settings, not alembic.ini. Two
   sources of truth is how you end up migrating one database and running the
   service against another, silently.

2. Batch mode on SQLite. SQLite cannot DROP COLUMN, change a type, or add a
   constraint in place; Alembic emulates those by rebuilding the table. It
   only does so when asked, and without it the first real schema change fails
   with an unhelpful error. Harmless on PostgreSQL, which alters properly.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Importing the package registers both tables on Base.metadata — see
# app/core/models/__init__.py. Without this Alembic sees an empty schema and
# cheerfully generates a migration that creates nothing.
from app.core.models import Base
from app.settings import get_settings

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database.url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=connection.dialect.name == "sqlite",
        # Notice type changes, not just added and removed columns.
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it — for review, or for a DBA."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_run)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
