"""Rate governor for the Meta Marketing API.

Meta meters the Marketing API per ad account in points: a read costs 1, a write
costs 3, against an hourly quota that scales with the account's spend. The default
developer tier is documented as unsuitable for production traffic. Exceeding the
quota does not merely fail the call — sustained abuse gets applications throttled
and accounts restricted.

This module is the reason the agent reads from ClickHouse. It exists to make the
small number of writes we *do* send provably safe:

* a local points budget, so we throttle ourselves before Meta has to;
* the ``X-Business-Use-Case-Usage`` / ``X-Ad-Account-Usage`` headers, which report
  actual server-side utilisation and are the only honest source of truth;
* Meta's own ``estimated_time_to_regain_access``, honoured rather than guessed at;
* a Postgres-backed breaker, so a restart cannot stampede a recovering account.
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from agent.config import MetaSettings
from agent.logging_setup import get_logger
from agent.ops.breaker import CircuitBreaker

log = get_logger(__name__)

# Meta's throttling error codes.
#   17    - user request limit reached
#   613   - calls to this API have exceeded the rate limit
#   80004 - ads management API rate limit (business use case)
#   4     - application request limit reached
THROTTLE_CODES = {4, 17, 613, 80004}


class RateLimitedError(RuntimeError):
    """Raised when a call is refused locally or by Meta for quota reasons."""

    def __init__(self, message: str, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class CircuitOpenError(RuntimeError):
    """Raised when the breaker is open and no call should be attempted."""


@dataclass(slots=True)
class UsageSnapshot:
    """Server-reported utilisation, parsed from response headers."""

    call_count_pct: float = 0.0
    total_cputime_pct: float = 0.0
    total_time_pct: float = 0.0
    estimated_time_to_regain_access: int = 0

    @property
    def worst_pct(self) -> float:
        return max(self.call_count_pct, self.total_cputime_pct, self.total_time_pct)


@dataclass
class RateGovernor:
    """A points-based token bucket plus header-driven backpressure."""

    settings: MetaSettings
    breaker: CircuitBreaker | None = None
    _spent_points: int = field(default=0, init=False)
    _window_started: float = field(default_factory=time.monotonic, init=False)
    _last_usage: UsageSnapshot = field(default_factory=UsageSnapshot, init=False)
    _verification_points: int = field(default=0, init=False)

    # ── Local budget ──────────────────────────────────────────────────────────

    def _roll_window(self) -> None:
        if time.monotonic() - self._window_started >= self.settings.rate_window_seconds:
            self._spent_points = 0
            self._verification_points = 0
            self._window_started = time.monotonic()

    @property
    def remaining_points(self) -> int:
        self._roll_window()
        return max(0, self.settings.window_points - self._spent_points)

    @property
    def last_usage(self) -> UsageSnapshot:
        return self._last_usage

    def check(self, *, is_write: bool, is_verification: bool = False) -> None:
        """Refuse a call locally before it is ever sent. Raises, or returns None."""
        self._roll_window()

        if self.breaker is not None:
            state = self.breaker.state()
            if state.is_open:
                raise CircuitOpenError(
                    f"Meta API circuit breaker open: {state.last_reason or 'unknown'}"
                )

        cost = self.settings.points_per_write if is_write else self.settings.points_per_read
        if self._spent_points + cost > self.settings.window_points:
            wait = self.settings.rate_window_seconds - (time.monotonic() - self._window_started)
            raise RateLimitedError(
                f"local points budget exhausted "
                f"({self._spent_points}/{self.settings.window_points})",
                retry_after_seconds=max(1, int(wait)),
            )

        # Verification reads are the single read path in this codebase, and they get
        # their own sub-budget so they can never crowd out the writes that matter.
        if is_verification:
            allowance = int(
                self.settings.window_points * self.settings.verification_budget_pct / 100
            )
            if self._verification_points + cost > allowance:
                raise RateLimitedError(
                    f"status-verification sub-budget exhausted "
                    f"({self._verification_points}/{allowance} points)"
                )

        # Server-reported utilisation overrides our local accounting: Meta knows
        # about calls from other processes using the same app, and we do not.
        worst = self._last_usage.worst_pct
        if worst >= self.settings.hard_utilization_pct:
            retry = self._last_usage.estimated_time_to_regain_access or 300
            if self.breaker is not None:
                self.breaker.trip(f"utilisation {worst:.0f}% >= hard limit", retry)
            raise RateLimitedError(
                f"Meta-reported utilisation {worst:.0f}% at or above hard limit "
                f"{self.settings.hard_utilization_pct:.0f}%",
                retry_after_seconds=retry,
            )

    def charge(self, *, is_write: bool, is_verification: bool = False) -> None:
        cost = self.settings.points_per_write if is_write else self.settings.points_per_read
        self._spent_points += cost
        if is_verification:
            self._verification_points += cost

    def throttle_delay(self) -> float:
        """Voluntary slow-down once utilisation crosses the soft threshold.

        Ramps from zero at the soft limit to a full second at the hard limit, with
        jitter so parallel workers do not resynchronise into a burst.
        """
        worst = self._last_usage.worst_pct
        soft, hard = self.settings.soft_utilization_pct, self.settings.hard_utilization_pct
        if worst < soft:
            return 0.0
        span = max(1e-6, hard - soft)
        ratio = min(1.0, (worst - soft) / span)
        return ratio * (1.0 + random.random() * 0.5)

    # ── Header parsing ────────────────────────────────────────────────────────

    def observe(self, response: httpx.Response) -> UsageSnapshot:
        snapshot = parse_usage_headers(response.headers)
        self._last_usage = snapshot
        if snapshot.worst_pct >= self.settings.soft_utilization_pct:
            log.warning(
                "meta.usage_high",
                call_count_pct=snapshot.call_count_pct,
                cputime_pct=snapshot.total_cputime_pct,
                total_time_pct=snapshot.total_time_pct,
            )
        return snapshot


def parse_usage_headers(headers: Any) -> UsageSnapshot:
    """Read Meta's usage headers.

    ``X-Business-Use-Case-Usage`` is a JSON map of account id -> list of usage
    objects; ``X-Ad-Account-Usage`` is a flat object. Both are best-effort — a
    malformed or absent header must never break a call, so this degrades to zeros.
    """
    snapshot = UsageSnapshot()

    raw_bucu = headers.get("x-business-use-case-usage") or headers.get("X-Business-Use-Case-Usage")
    if raw_bucu:
        try:
            parsed = json.loads(raw_bucu)
            for entries in parsed.values():
                for entry in entries:
                    snapshot.call_count_pct = max(
                        snapshot.call_count_pct, float(entry.get("call_count", 0))
                    )
                    snapshot.total_cputime_pct = max(
                        snapshot.total_cputime_pct, float(entry.get("total_cputime", 0))
                    )
                    snapshot.total_time_pct = max(
                        snapshot.total_time_pct, float(entry.get("total_time", 0))
                    )
                    snapshot.estimated_time_to_regain_access = max(
                        snapshot.estimated_time_to_regain_access,
                        int(entry.get("estimated_time_to_regain_access", 0) or 0),
                    )
        except (ValueError, TypeError, AttributeError):
            log.warning("meta.usage_header_unparseable", header="x-business-use-case-usage")

    raw_acct = headers.get("x-ad-account-usage") or headers.get("X-Ad-Account-Usage")
    if raw_acct:
        try:
            parsed_acct = json.loads(raw_acct)
            snapshot.call_count_pct = max(
                snapshot.call_count_pct, float(parsed_acct.get("acc_id_util_pct", 0))
            )
        except (ValueError, TypeError, AttributeError):
            log.warning("meta.usage_header_unparseable", header="x-ad-account-usage")

    return snapshot


def extract_error(payload: dict[str, Any]) -> tuple[int | None, str, int | None]:
    """Pull (code, message, retry_after) out of a Graph API error body."""
    error = payload.get("error") or {}
    code = error.get("code")
    message = error.get("message") or error.get("error_user_msg") or "unknown Meta API error"
    retry_after = None
    blame = error.get("error_data") or {}
    if isinstance(blame, dict):
        retry_after = blame.get("estimated_time_to_regain_access")
    return (int(code) if code is not None else None, str(message), retry_after)
