"""Meta Marketing API client — mutations only.

## The constraint

This client can publish, pause, resume, and re-budget. It cannot read performance
data, because no method exists to do so. That is not a convention to be remembered;
``tests/test_meta_write_only.py`` asserts the public surface contains no insights or
reporting endpoint, so adding one breaks the build.

Performance data is read from ClickHouse. Polling ``/insights`` on a schedule is the
standard way to burn an ad account's quota and get an app restricted, and it buys
nothing the warehouse does not already hold with better joins.

## The one exception

``verify_object_status`` reads back a single object's status after a mutation.
Claiming literally zero reads would be false: after an ambiguous timeout, there is no
other way to learn whether a write landed. It is bounded instead — a dedicated
sub-budget (default 5% of quota), one object at a time, no insights fields, and it
can be switched off entirely with ``allow_status_verification=False``.

## Safety posture

* ``dry_run`` defaults to True. A misconfigured deploy spends nothing.
* Every mutation claims an idempotency key *before* the request is sent.
* All calls pass the rate governor and the persisted circuit breaker.
"""

from __future__ import annotations

import hashlib
import time
from decimal import Decimal
from typing import Any

import httpx

from agent.config import MetaSettings, Settings, get_settings
from agent.domain import ActionType, Decision
from agent.logging_setup import get_logger
from agent.meta import payloads
from agent.meta.rate_governor import (
    THROTTLE_CODES,
    CircuitOpenError,
    RateGovernor,
    RateLimitedError,
    extract_error,
)
from agent.ops.breaker import CircuitBreaker
from agent.ops.ledger import IdempotencyStore

log = get_logger(__name__)

# Enumerated so the write-only property is machine-checkable. Anything that mutates
# the ad account must appear here; nothing that reads may.
WRITE_METHODS = frozenset(
    {
        "create_campaign",
        "create_adset",
        "create_ad",
        "pause_ad",
        "resume_ad",
        "update_adset_budget",
    }
)


class MetaWriteClient:
    def __init__(
        self,
        settings: Settings | None = None,
        governor: RateGovernor | None = None,
        breaker: CircuitBreaker | None = None,
        idempotency: IdempotencyStore | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        resolved = settings or get_settings()
        self._settings: MetaSettings = resolved.meta
        self._breaker = breaker
        self._governor = governor or RateGovernor(self._settings, breaker)
        self._idempotency = idempotency
        self._http = client or httpx.Client(timeout=30.0)

    # ── Mutations ─────────────────────────────────────────────────────────────

    def create_campaign(self, name: str, objective: str = "OUTCOME_SALES") -> dict[str, Any]:
        return self._write(
            f"{self._settings.ad_account_id}/campaigns",
            payloads.campaign_payload(name, objective),
            idem=f"campaign:{name}",
        )

    def create_adset(
        self,
        name: str,
        campaign_id: str,
        daily_budget: Decimal,
        targeting: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._write(
            f"{self._settings.ad_account_id}/adsets",
            payloads.adset_payload(name, campaign_id, daily_budget, targeting=targeting),
            idem=f"adset:{campaign_id}:{name}",
        )

    def create_ad(
        self, name: str, adset_id: str, creative_id: str, tracking_ad_id: str | None = None
    ) -> dict[str, Any]:
        return self._write(
            f"{self._settings.ad_account_id}/ads",
            payloads.ad_payload(name, adset_id, creative_id, tracking_ad_id),
            idem=f"ad:{adset_id}:{name}",
        )

    def pause_ad(self, ad_id: str) -> dict[str, Any]:
        return self._write(ad_id, payloads.status_payload("PAUSED"), idem=f"pause:{ad_id}")

    def resume_ad(self, ad_id: str) -> dict[str, Any]:
        return self._write(ad_id, payloads.status_payload("ACTIVE"), idem=f"resume:{ad_id}")

    def update_adset_budget(self, adset_id: str, new_daily_budget: Decimal) -> dict[str, Any]:
        return self._write(
            adset_id,
            payloads.budget_update_payload(new_daily_budget),
            idem=f"budget:{adset_id}:{new_daily_budget}",
        )

    # ── The single, bounded read ──────────────────────────────────────────────

    def verify_object_status(self, object_id: str) -> dict[str, Any] | None:
        """Read back one object's status. Never insights, never in bulk.

        Returns None when verification is disabled or its sub-budget is spent —
        callers treat that as "unverified", not as failure.
        """
        if not self._settings.allow_status_verification:
            return None
        if self._settings.dry_run:
            return {"id": object_id, "status": "DRY_RUN", "dry_run": True}

        try:
            self._governor.check(is_write=False, is_verification=True)
        except (RateLimitedError, CircuitOpenError) as exc:
            log.warning("meta.verify_skipped", object_id=object_id, reason=str(exc))
            return None

        response = self._http.get(
            f"{self._settings.base_url}/{object_id}",
            params={
                "fields": "id,status,effective_status",  # status only, by design
                "access_token": self._settings.access_token.get_secret_value(),
            },
        )
        self._governor.observe(response)
        self._governor.charge(is_write=False, is_verification=True)
        if response.status_code >= 400:
            return None
        return dict(response.json())

    # ── Executor interface used by the decision engine ────────────────────────

    def execute(self, decision: Decision) -> dict[str, Any]:
        """Apply a Decision. Satisfies ``decision.engine.ActionExecutor``."""
        if decision.action is ActionType.PAUSE_AD:
            if not decision.ad_id:
                raise ValueError("pause_ad decision missing ad_id")
            return self.pause_ad(decision.ad_id)

        if decision.action is ActionType.RESUME_AD:
            if not decision.ad_id:
                raise ValueError("resume_ad decision missing ad_id")
            return self.resume_ad(decision.ad_id)

        if decision.action is ActionType.SCALE_BUDGET:
            if not decision.adset_id:
                raise ValueError("scale_budget decision missing adset_id")
            new_budget = decision.params.get("new_budget")
            if new_budget is None:
                raise ValueError("scale_budget decision missing new_budget")
            return self.update_adset_budget(decision.adset_id, Decimal(str(new_budget)))

        raise ValueError(f"{decision.action} is not an executable mutation")

    # ── Transport ─────────────────────────────────────────────────────────────

    def _write(self, path: str, data: dict[str, Any], idem: str) -> dict[str, Any]:
        key = _idempotency_key(self._settings.ad_account_id, path, idem)

        if self._settings.dry_run:
            log.info("meta.dry_run_write", path=path, payload=data, idempotency_key=key)
            return {"dry_run": True, "path": path, "payload": data, "idempotency_key": key}

        # Claim before sending. If the process dies between request and response, the
        # retry finds the key taken and does not create a second ad.
        if self._idempotency is not None and not self._idempotency.claim(key):
            cached = self._idempotency.get_result(key)
            log.warning("meta.write_replayed", path=path, idempotency_key=key)
            return cached or {"replayed": True, "idempotency_key": key}

        self._governor.check(is_write=True)

        delay = self._governor.throttle_delay()
        if delay > 0:
            log.info("meta.self_throttle", seconds=round(delay, 2))
            time.sleep(delay)

        response = self._http.post(
            f"{self._settings.base_url}/{path}",
            data={**data, "access_token": self._settings.access_token.get_secret_value()},
        )
        self._governor.observe(response)
        self._governor.charge(is_write=True)

        payload = _safe_json(response)

        if response.status_code >= 400:
            code, message, retry_after = extract_error(payload)
            if code in THROTTLE_CODES:
                cooldown = retry_after or self._governor.last_usage.estimated_time_to_regain_access
                if self._breaker is not None:
                    # Honour Meta's own estimate rather than inventing a backoff.
                    self._breaker.trip(f"throttled (code {code}): {message}", cooldown or 300)
                raise RateLimitedError(
                    f"Meta throttled request (code {code}): {message}",
                    retry_after_seconds=cooldown,
                )
            if self._breaker is not None:
                self._breaker.record_failure(f"HTTP {response.status_code}: {message}")
            raise RuntimeError(f"Meta API error {response.status_code} (code {code}): {message}")

        if self._breaker is not None:
            self._breaker.record_success()
        if self._idempotency is not None:
            self._idempotency.store_result(key, payload)

        log.info("meta.write_ok", path=path, response_id=payload.get("id"))
        return payload

    def close(self) -> None:
        self._http.close()


def _idempotency_key(account_id: str, path: str, discriminator: str) -> str:
    digest = hashlib.sha256(f"{account_id}|{path}|{discriminator}".encode()).hexdigest()
    return f"meta_{digest[:32]}"


def _safe_json(response: httpx.Response) -> dict[str, Any]:
    try:
        value = response.json()
    except ValueError:
        return {"raw": response.text[:2000]}
    return value if isinstance(value, dict) else {"data": value}
