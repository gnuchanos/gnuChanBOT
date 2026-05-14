"""Filesystem helpers for local SQLite deployments."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.engine.url import make_url


def ensure_sqlite_parent_dir(database_url: str) -> None:
    """Create parent directories for a file-based SQLite database if needed."""

    url = make_url(database_url)
    if not url.drivername.startswith("sqlite"):
        return
    if url.database in (None, "", ":memory:"):
        return
    path = Path(url.database)
    if not path.name:
        return
    path.expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
