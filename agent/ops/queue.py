"""Durable job queue.

``FOR UPDATE SKIP LOCKED`` lets several workers drain the same table without
coordination and without handing the same job to two of them. Creative generation
can take minutes, so an in-memory queue would lose work on every deploy.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from agent.logging_setup import get_logger
from agent.ops.db import Database

log = get_logger(__name__)


@dataclass(slots=True)
class Job:
    id: int
    kind: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int


class JobQueue:
    def __init__(self, db: Database) -> None:
        self._db = db

    def enqueue(
        self,
        kind: str,
        payload: dict[str, Any] | None = None,
        *,
        delay_seconds: int = 0,
        max_attempts: int = 3,
    ) -> int:
        run_after = datetime.now().astimezone() + timedelta(seconds=delay_seconds)
        with self._db.cursor() as cur:
            cur.execute(
                "INSERT INTO jobs (kind, payload, run_after, max_attempts) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (kind, json.dumps(payload or {}), run_after, max_attempts),
            )
            row = cur.fetchone()
        job_id = int(row["id"])  # type: ignore[index]
        log.info("queue.enqueued", job_id=job_id, kind=kind)
        return job_id

    def claim(self) -> Job | None:
        """Atomically take the next runnable job, or return None."""
        with self._db.cursor() as cur:
            cur.execute(
                """
                UPDATE jobs SET status = 'running',
                                locked_at = now(),
                                attempts = attempts + 1,
                                updated_at = now()
                WHERE id = (
                    SELECT id FROM jobs
                    WHERE status = 'pending' AND run_after <= now()
                    ORDER BY run_after
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                RETURNING id, kind, payload, attempts, max_attempts
                """
            )
            row = cur.fetchone()
        if row is None:
            return None
        return Job(
            id=int(row["id"]),
            kind=str(row["kind"]),
            payload=dict(row["payload"]),
            attempts=int(row["attempts"]),
            max_attempts=int(row["max_attempts"]),
        )

    def succeed(self, job_id: int) -> None:
        with self._db.cursor() as cur:
            cur.execute(
                "UPDATE jobs SET status = 'succeeded', updated_at = now() WHERE id = %s",
                (job_id,),
            )

    def fail(self, job: Job, error: str) -> None:
        """Retry with exponential backoff until ``max_attempts``, then park as dead."""
        exhausted = job.attempts >= job.max_attempts
        status = "dead" if exhausted else "pending"
        backoff = min(2**job.attempts, 900)
        with self._db.cursor() as cur:
            cur.execute(
                """
                UPDATE jobs
                SET status = %s,
                    last_error = %s,
                    run_after = now() + make_interval(secs => %s),
                    locked_at = NULL,
                    updated_at = now()
                WHERE id = %s
                """,
                (status, error[:4000], backoff, job.id),
            )
        log.warning(
            "queue.job_failed",
            job_id=job.id,
            kind=job.kind,
            attempts=job.attempts,
            dead=exhausted,
            error=error[:200],
        )

    def requeue_stalled(self, older_than_minutes: int = 30) -> int:
        """Recover jobs whose worker died holding them."""
        with self._db.cursor() as cur:
            cur.execute(
                """
                UPDATE jobs SET status = 'pending', locked_at = NULL, updated_at = now()
                WHERE status = 'running'
                  AND locked_at < now() - make_interval(mins => %s)
                """,
                (older_than_minutes,),
            )
            return cur.rowcount
