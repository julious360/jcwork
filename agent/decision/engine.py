"""The feedback loop.

Reads the warehouse, decides, records, and (unless dry-running) executes. The engine
depends on an ``ActionExecutor`` protocol rather than on the Meta client directly, so
the entire decision path is testable without credentials or network access.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Protocol

from agent.config import ThresholdConfig
from agent.decision.guardrails import GuardrailContext
from agent.decision.rules import evaluate_ad
from agent.domain import ActionStatus, ActionType, AdEconomics, Decision
from agent.logging_setup import get_logger
from agent.ops.ledger import ActionLedger

log = get_logger(__name__)


class ActionExecutor(Protocol):
    """What the engine needs from a thing that can change the ad account."""

    def execute(self, decision: Decision) -> dict[str, Any]: ...


@dataclass(slots=True)
class LoopResult:
    run_id: uuid.UUID
    evaluated: int = 0
    decisions: list[Decision] = field(default_factory=list)
    executed: int = 0
    failed: int = 0
    skipped_for_approval: int = 0

    @property
    def actionable(self) -> list[Decision]:
        return [d for d in self.decisions if not d.is_no_op]

    def counts_by_action(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for decision in self.decisions:
            counts[str(decision.action)] = counts.get(str(decision.action), 0) + 1
        return counts


class DecisionEngine:
    def __init__(
        self,
        ledger: ActionLedger,
        thresholds: ThresholdConfig,
        executor: ActionExecutor | None = None,
    ) -> None:
        self._ledger = ledger
        self._cfg = thresholds
        self._executor = executor

    def run(self, economics: list[AdEconomics], *, dry_run: bool = True) -> LoopResult:
        run_id = uuid.uuid4()
        result = LoopResult(run_id=run_id)

        actions_today = self._ledger.actions_today()
        # Adset-level spend decides whether an action needs human approval; an
        # individual ad's spend understates the blast radius of a budget change.
        adset_spend = _adset_spend(economics)

        log.info(
            "loop.start",
            run_id=str(run_id),
            ads=len(economics),
            dry_run=dry_run,
            actions_today=actions_today,
        )

        actions_this_run = 0
        for econ in sorted(economics, key=lambda e: e.lifetime_spend, reverse=True):
            ctx = GuardrailContext(
                actions_this_run=actions_this_run,
                actions_today=actions_today,
                last_scale_at=self._ledger.last_scale_at(econ.adset_id),
                adset_spend=adset_spend.get(econ.adset_id, Decimal("0")),
            )

            decision = evaluate_ad(econ, self._cfg, ctx)
            result.evaluated += 1
            result.decisions.append(decision)

            if decision.is_no_op:
                continue

            action_id = self._ledger.record(run_id, decision, dry_run=dry_run)
            actions_this_run += 1

            if dry_run:
                log.info(
                    "loop.decision_dry_run",
                    action=str(decision.action),
                    ad_id=decision.ad_id,
                    reason=decision.reason,
                )
                continue

            if decision.requires_approval:
                result.skipped_for_approval += 1
                log.info("loop.awaiting_approval", action_id=action_id, ad_id=decision.ad_id)
                continue

            self._execute(action_id, decision, result)

        log.info(
            "loop.done",
            run_id=str(run_id),
            evaluated=result.evaluated,
            actionable=len(result.actionable),
            executed=result.executed,
            failed=result.failed,
        )
        return result

    def _execute(self, action_id: int, decision: Decision, result: LoopResult) -> None:
        if self._executor is None:
            self._ledger.mark(action_id, ActionStatus.SKIPPED, error="no executor configured")
            return
        try:
            response = self._executor.execute(decision)
            self._ledger.mark(action_id, ActionStatus.EXECUTED, meta_response=response)
            result.executed += 1
            log.info("loop.executed", action=str(decision.action), ad_id=decision.ad_id)
        except Exception as exc:
            self._ledger.mark(action_id, ActionStatus.FAILED, error=str(exc))
            result.failed += 1
            log.error(
                "loop.execute_failed",
                action=str(decision.action),
                ad_id=decision.ad_id,
                error=str(exc),
            )


def default_lookback(cfg: ThresholdConfig, today: date | None = None) -> date:
    """Earliest day the loop should load.

    Covers the attribution lookback plus the maturity lag, with a small buffer, so
    that every day capable of still changing is re-read.
    """
    reference = today or date.today()
    days = cfg.attribution.lookback_days + (cfg.attribution.lag_hours // 24) + 3
    return reference - timedelta(days=days)


def _adset_spend(economics: list[AdEconomics]) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = {}
    for econ in economics:
        totals[econ.adset_id] = totals.get(econ.adset_id, Decimal("0")) + econ.lifetime_spend
    return totals


__all__ = [
    "ActionExecutor",
    "ActionStatus",
    "ActionType",
    "DecisionEngine",
    "LoopResult",
    "default_lookback",
]
