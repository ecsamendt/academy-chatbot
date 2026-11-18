"""Postgres connection pool and a tiny migration runner."""

from __future__ import annotations

from importlib import resources

from pgvector.psycopg import register_vector
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import get_settings

_pool: ConnectionPool | None = None


def _configure(conn: Connection) -> None:
    # The vector type exists only after the first migration has run.
    try:
        register_vector(conn)
    except Exception:
        conn.rollback()
    conn.row_factory = dict_row


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            get_settings().database_url,
            min_size=1,
            max_size=10,
            configure=_configure,
            open=True,
        )
    return _pool


def run_migrations() -> list[str]:
    """Apply any app/migrations/*.sql files not yet recorded. Returns names applied."""
    settings = get_settings()
    applied: list[str] = []
    files = sorted(
        (p for p in resources.files("app.migrations").iterdir() if p.name.endswith(".sql")),
        key=lambda p: p.name,
    )
    with Connection.connect(settings.database_url, autocommit=False) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        done = {r[0] for r in conn.execute("SELECT name FROM schema_migrations").fetchall()}
        for f in files:
            if f.name in done:
                continue
            conn.execute(f.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (f.name,))
            applied.append(f.name)
        conn.commit()
    # Re-create the pool so new connections register the vector type.
    global _pool
    if applied and _pool is not None:
        _pool.close()
        _pool = None
    return applied
