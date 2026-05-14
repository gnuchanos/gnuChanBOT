"""Async database engine and session factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from gnubot.models import Base

logger = logging.getLogger(__name__)


def create_engine(database_url: str) -> AsyncEngine:
    """Build an async SQLAlchemy engine from a URL."""

    kwargs: dict = {"echo": False}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_async_engine(database_url, **kwargs)


async def init_schema(engine: AsyncEngine) -> None:
    """Create tables if they do not exist (bootstrap for single-node deploys)."""

    def _ensure_roblox_unique_index(sync_conn) -> None:
        dialect = sync_conn.dialect.name
        if dialect not in ("sqlite", "postgresql"):
            return
        try:
            sync_conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_roblox_id_notnull "
                    "ON users (roblox_id) WHERE roblox_id IS NOT NULL"
                )
            )
            logger.info("Partial unique index uq_users_roblox_id_notnull ensured on users(roblox_id).")
        except Exception:
            logger.warning(
                "Partial unique index on users(roblox_id) was not applied "
                "(duplicate Roblox rows, permissions, or engine). Clean duplicates and restart.",
                exc_info=True,
            )

    def _sqlite_pragmas(sync_conn) -> None:
        if sync_conn.dialect.name != "sqlite":
            return
        try:
            sync_conn.execute(text("PRAGMA journal_mode=WAL"))
            sync_conn.execute(text("PRAGMA synchronous=NORMAL"))
            logger.info("SQLite PRAGMAs: journal_mode=WAL, synchronous=NORMAL.")
        except Exception:
            logger.warning("SQLite PRAGMA setup skipped.", exc_info=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_sqlite_pragmas)
        await conn.run_sync(_ensure_roblox_unique_index)
    logger.info("Database schema ensured (create_all + optional indexes).")


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


@asynccontextmanager
async def open_session(
    maker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    session = maker()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
