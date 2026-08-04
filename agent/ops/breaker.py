"""Persisted circuit breaker for the Meta API.

State lives in Postgres, not memory, and that is the whole point. An in-memory
breaker resets to "closed" on every deploy — which is exactly the moment you least
want a burst of writes at an ad account that is already throttling you.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from agent.logging_setup import get_logger
from agent.ops.db import Database

log = get_logger(__name__)

META_BREAKER = "meta_marketing_api"


@dataclass(slots=True)
class BreakerState:
    name: str
    state: str
    failure_count: int
    reopen_after: datetime | None
    last_reason: str | None

    @property
    def is_open(self) -> bool:
        if self.state != "open":
            return False
        if self.reopen_after is None:
            return True
        # Cooldown elapsed: the caller may probe once (half-open).
        return datetime.now().astimezone() < self.reopen_after


class CircuitBreaker:
    def __init__(self, db: Database, name: str = META_BREAKER, threshold: int = 5) -> None:
        self._db = db
        self._name = name
        self._threshold = threshold

    def state(self) -> BreakerState:
        with self._db.cursor() as cur:
            cur.execute(
                "INSERT INTO circuit_breaker (name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
                (self._name,),
            )
            cur.execute(
                "SELECT name, state, failure_count, reopen_after, last_reason "
                "FROM circuit_breaker WHERE name = %s",
                (self._name,),
            )
            row = cur.fetchone()
        return BreakerState(
            name=str(row["name"]),  # type: ignore[index]
            state=str(row["state"]),  # type: ignore[index]
            failure_count=int(row["failure_count"]),  # type: ignore[index]
            reopen_after=row["reopen_after"],  # type: ignore[index]
            last_reason=row["last_reason"],  # type: ignore[index]
        )

    def record_success(self) -> None:
        with self._db.cursor() as cur:
            cur.execute(
                "UPDATE circuit_breaker SET state = 'closed', failure_count = 0, "
                "opened_at = NULL, reopen_after = NULL, updated_at = now() WHERE name = %s",
                (self._name,),
            )

    def record_failure(self, reason: str, cooldown_seconds: int | None = None) -> BreakerState:
        """Count a failure; trip the breaker once the threshold is crossed.

        ``cooldown_seconds`` should be Meta's own ``estimated_time_to_regain_access``
        when it supplies one — guessing a backoff when the platform has told you the
        answer is how you stay throttled.
        """
        self.state()  # ensure the row exists
        with self._db.cursor() as cur:
            cur.execute(
                "SELECT failure_count FROM circuit_breaker WHERE name = %s FOR UPDATE",
                (self._name,),
            )
            row = cur.fetchone()
            failures = int(row["failure_count"]) + 1  # type: ignore[index]
            tripped = failures >= self._threshold or cooldown_seconds is not None
            cooldown = cooldown_seconds if cooldown_seconds is not None else 300

            if tripped:
                reopen = datetime.now().astimezone() + timedelta(seconds=cooldown)
                cur.execute(
                    "UPDATE circuit_breaker SET state = 'open', failure_count = %s, "
                    "opened_at = now(), reopen_after = %s, last_reason = %s, "
                    "updated_at = now() WHERE name = %s",
                    (failures, reopen, reason[:2000], self._name),
                )
                log.error(
                    "breaker.opened", name=self._name, reason=reason[:200], cooldown_s=cooldown
                )
            else:
                cur.execute(
                    "UPDATE circuit_breaker SET failure_count = %s, last_reason = %s, "
                    "updated_at = now() WHERE name = %s",
                    (failures, reason[:2000], self._name),
                )
        return self.state()

    def trip(self, reason: str, cooldown_seconds: int) -> None:
        """Open the breaker immediately, bypassing the failure threshold."""
        self.record_failure(reason, cooldown_seconds=cooldown_seconds)
