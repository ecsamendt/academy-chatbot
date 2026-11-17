"""Durable job queue on Postgres (SELECT ... FOR UPDATE SKIP LOCKED)."""

from __future__ import annotations

from psycopg.types.json import Jsonb

from app.db import get_pool

MAX_ATTEMPTS = 3


def enqueue(kind: str, payload: dict | None = None) -> int:
    with get_pool().connection() as conn:
        row = conn.execute(
            "INSERT INTO jobs (kind, payload) VALUES (%s, %s) RETURNING id",
            (kind, Jsonb(payload or {})),
        ).fetchone()
        return row["id"]


def claim_next() -> dict | None:
    with get_pool().connection() as conn:
        return conn.execute(
            """
            UPDATE jobs SET status = 'running', attempts = attempts + 1, updated_at = now()
            WHERE id = (
                SELECT id FROM jobs WHERE status = 'queued'
                ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1)
            RETURNING id, kind, payload, attempts
            """
        ).fetchone()


def finish(job_id: int) -> None:
    with get_pool().connection() as conn:
        conn.execute("UPDATE jobs SET status = 'done', error = NULL, updated_at = now() WHERE id = %s", (job_id,))


def fail(job_id: int, attempts: int, error: str) -> None:
    status = "failed" if attempts >= MAX_ATTEMPTS else "queued"
    with get_pool().connection() as conn:
        conn.execute(
            "UPDATE jobs SET status = %s, error = %s, updated_at = now() WHERE id = %s",
            (status, error[:2000], job_id),
        )


def requeue_stuck(minutes: int = 60) -> None:
    """Jobs left 'running' by a crashed worker go back in the queue."""
    with get_pool().connection() as conn:
        conn.execute(
            "UPDATE jobs SET status = 'queued' WHERE status = 'running' "
            "AND updated_at < now() - make_interval(mins => %s)",
            (minutes,),
        )
