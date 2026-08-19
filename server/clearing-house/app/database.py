"""Database connection lifecycle.

Owns one engine for the process, applies the SQLite settings the hot path
depends on, and hands out sessions.

Deliberately does NOT create tables. Schema comes from migrations, in every
environment, so development and production follow the same path and schema
drift cannot hide behind a convenient create_all().
"""

import logging
from typing import AsyncIterator, Optional

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger("ds_clearing_house.database")


def _register_sqlite_pragmas(engine: AsyncEngine) -> None:
    """Apply SQLite settings to every new connection.

    PRAGMAs are per-connection, not per-database, so setting them once at
    startup would leave every later connection on the defaults. Hooking the
    driver's connect event is the only way to be sure.
    """

    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()

        # Without WAL, SQLite blocks readers for the duration of any write.
        # The Contract Validator's status lookup sits on the hot path of
        # every data access and blocks on the answer, so it must not queue
        # behind an unrelated append to the history log.
        cursor.execute("PRAGMA journal_mode=WAL")

        # Default behaviour when another writer holds the lock is to fail
        # immediately. Wait instead. 5s is not arbitrary: the Generator's
        # HTTP timeout is 5s with no retries, so waiting longer would only
        # produce an answer nobody is still listening for.
        cursor.execute("PRAGMA busy_timeout=5000")

        # SQLite ignores foreign keys entirely unless asked.
        cursor.execute("PRAGMA foreign_keys=ON")

        cursor.close()


class Database:
    """Holds the engine and session factory for the process lifetime."""

    def __init__(self, url: str, echo: bool = False) -> None:
        self._url = url
        self._echo = echo
        self._engine: Optional[AsyncEngine] = None
        self._sessions: Optional[async_sessionmaker[AsyncSession]] = None

    @property
    def engine(self) -> AsyncEngine:
        if self._engine is None:
            raise RuntimeError("Database.connect() has not been called")
        return self._engine

    async def connect(self) -> None:
        self._engine = create_async_engine(self._url, echo=self._echo)

        if self._url.startswith("sqlite"):
            _register_sqlite_pragmas(self._engine)

        self._sessions = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            # Keep attributes readable after commit(). Without this, touching
            # a field post-commit triggers a lazy refresh, which in async code
            # raises rather than quietly re-querying.
            expire_on_commit=False,
        )
        logger.info("database connected url=%s", self._safe_url())

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
        self._engine = None
        self._sessions = None

    def session(self) -> AsyncSession:
        """A new unit of work. The caller is responsible for closing it."""
        if self._sessions is None:
            raise RuntimeError("Database.connect() has not been called")
        return self._sessions()

    def _safe_url(self) -> str:
        """URL with any password removed, for logging."""
        if "@" not in self._url:
            return self._url
        scheme, rest = self._url.split("://", 1)
        return f"{scheme}://***@{rest.split('@', 1)[1]}"


# One instance per process, created at import time in main.py from settings.
_database: Optional[Database] = None


def init_database(url: str, echo: bool = False) -> Database | None:
    global _database
    _database = Database(url, echo)
    return _database


def get_database() -> Database:
    if _database is None:
        raise RuntimeError("init_database() has not been called")
    return _database


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, always closed."""
    session = get_database().session()
    try:
        yield session
    finally:
        await session.close()
