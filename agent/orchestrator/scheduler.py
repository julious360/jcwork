"""Scheduler: enqueues recurring work.

Deliberately a long-running loop with its own cadence tracking rather than a cron
expression per job. The decision interval is operator-tunable in ``thresholds.yaml``,
and enqueueing (rather than executing) keeps the scheduler cheap and crash-safe —
if it dies, the worker still drains whatever was already queued.
"""

from __future__ import annotations

import signal
import time
from dataclasses import dataclass
from types import FrameType

from agent.config import Settings, get_settings, load_thresholds
from agent.logging_setup import get_logger
from agent.ops.db import Database
from agent.ops.queue import JobQueue
from agent.orchestrator.jobs import (
    JOB_HARVEST_ENTROPY,
    JOB_REFRESH_WAREHOUSE,
    JOB_RESEARCH,
)

log = get_logger(__name__)


@dataclass(slots=True)
class ScheduleEntry:
    kind: str
    interval_seconds: float
    payload: dict[str, object]
    last_run: float = 0.0

    def due(self, now: float) -> bool:
        return now - self.last_run >= self.interval_seconds


class Scheduler:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._queue = JobQueue(Database(self._settings))
        thresholds = load_thresholds()

        self._entries = [
            # The feedback loop. Refreshing the warehouse chains into the decision
            # loop, so this single entry drives the whole optimisation cycle.
            ScheduleEntry(
                kind=JOB_REFRESH_WAREHOUSE,
                interval_seconds=thresholds.check_interval_hours * 3600,
                payload={"days": 30, "dry_run": self._settings.meta.dry_run},
            ),
            # Entropy injection, daily. Slower cadence than the loop on purpose:
            # external sources do not change hour to hour.
            ScheduleEntry(
                kind=JOB_HARVEST_ENTROPY,
                interval_seconds=24 * 3600,
                payload={"limit": 20},
            ),
            # Research, weekly. Pain points are stable over days, not hours.
            ScheduleEntry(
                kind=JOB_RESEARCH,
                interval_seconds=7 * 24 * 3600,
                payload={"limit": 50},
            ),
        ]
        self._running = True

    def stop(self, signum: int | None = None, frame: FrameType | None = None) -> None:
        log.info("scheduler.stopping", signal=signum)
        self._running = False

    def tick(self, run_immediately: bool = False) -> list[str]:
        """Enqueue everything due. Returns the kinds enqueued."""
        now = time.monotonic()
        enqueued: list[str] = []
        for entry in self._entries:
            if run_immediately or entry.due(now):
                self._queue.enqueue(entry.kind, dict(entry.payload))
                entry.last_run = now
                enqueued.append(entry.kind)
        return enqueued

    def run_forever(self) -> None:
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)

        log.info(
            "scheduler.started",
            entries=[e.kind for e in self._entries],
            dry_run=self._settings.meta.dry_run,
        )
        # Prime on boot so a fresh deploy does not idle for a full interval.
        self.tick(run_immediately=True)

        while self._running:
            time.sleep(30)
            if not self._running:
                break
            enqueued = self.tick()
            if enqueued:
                log.info("scheduler.enqueued", kinds=enqueued)

        log.info("scheduler.stopped")
