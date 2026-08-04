"""Queue worker: claim a job, run its handler, record the outcome."""

from __future__ import annotations

import signal
import time
from types import FrameType

from agent.config import Settings, get_settings
from agent.logging_setup import get_logger
from agent.orchestrator.jobs import HANDLERS, JobContext

log = get_logger(__name__)


class Worker:
    def __init__(self, settings: Settings | None = None, poll_seconds: float = 2.0) -> None:
        self._settings = settings or get_settings()
        self._ctx = JobContext.build(self._settings)
        self._poll = poll_seconds
        self._running = True

    def stop(self, signum: int | None = None, frame: FrameType | None = None) -> None:
        """Finish the current job, then exit — never abandon work mid-flight."""
        log.info("worker.stopping", signal=signum)
        self._running = False

    def run_once(self) -> bool:
        """Process one job. Returns False when the queue is empty."""
        job = self._ctx.queue.claim()
        if job is None:
            return False

        handler = HANDLERS.get(job.kind)
        if handler is None:
            self._ctx.queue.fail(job, f"no handler registered for kind {job.kind!r}")
            return True

        log.info("worker.job_start", job_id=job.id, kind=job.kind, attempt=job.attempts)
        try:
            result = handler(self._ctx, job.payload)
            self._ctx.queue.succeed(job.id)
            log.info("worker.job_done", job_id=job.id, kind=job.kind, result=result)
        except Exception as exc:
            self._ctx.queue.fail(job, f"{type(exc).__name__}: {exc}")
        return True

    def run_forever(self) -> None:
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)

        log.info("worker.started", environment=self._settings.environment)
        last_sweep = 0.0

        while self._running:
            # Recover jobs whose worker died holding them.
            if time.monotonic() - last_sweep > 300:
                requeued = self._ctx.queue.requeue_stalled()
                if requeued:
                    log.info("worker.requeued_stalled", count=requeued)
                last_sweep = time.monotonic()

            if not self.run_once():
                time.sleep(self._poll)

        log.info("worker.stopped")
