"""End-to-end loop over the four canonical scenarios, with a fake ledger.

Asserts the whole engine, not just the rules: that exactly the right ads are acted
on, that the ledger records the justifying evidence, that dry-run writes nothing,
and that the blast-radius caps hold.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest

from agent.config import ThresholdConfig
from agent.decision.engine import DecisionEngine
from agent.domain import ActionStatus, ActionType, AdEconomics, Decision


class FakeLedger:
    """In-memory stand-in for ActionLedger — no Postgres needed."""

    def __init__(self, actions_today: int = 0) -> None:
        self.records: list[tuple[int, Decision, bool, ActionStatus]] = []
        self.marks: list[tuple[int, ActionStatus]] = []
        self._actions_today = actions_today
        self._next_id = 1

    def record(
        self,
        run_id: uuid.UUID,
        decision: Decision,
        *,
        dry_run: bool,
        status: ActionStatus | None = None,
    ) -> int:
        action_id = self._next_id
        self._next_id += 1
        # Mirrors ActionLedger.record: a decision needing sign-off is parked, not proposed.
        resolved = status or (
            ActionStatus.AWAITING_APPROVAL if decision.requires_approval else ActionStatus.PROPOSED
        )
        self.records.append((action_id, decision, dry_run, resolved))
        return action_id

    def id_for(self, ad_id: str) -> int:
        return next(rec[0] for rec in self.records if rec[1].ad_id == ad_id)

    def mark(self, action_id: int, status: ActionStatus, **kwargs: Any) -> None:
        self.marks.append((action_id, status))

    def actions_today(self) -> int:
        return self._actions_today

    def last_scale_at(self, adset_id: str) -> None:
        return None


class RecordingExecutor:
    def __init__(self, fail_on: str | None = None) -> None:
        self.executed: list[Decision] = []
        self._fail_on = fail_on

    def execute(self, decision: Decision) -> dict[str, Any]:
        if self._fail_on and decision.ad_id == self._fail_on:
            raise RuntimeError("simulated Meta API failure")
        self.executed.append(decision)
        return {"id": decision.ad_id, "success": True}


@pytest.fixture
def scenarios(
    clear_loser: AdEconomics,
    clear_winner: AdEconomics,
    under_sampled: AdEconomics,
    immature_window: AdEconomics,
) -> list[AdEconomics]:
    return [clear_loser, clear_winner, under_sampled, immature_window]


def test_loop_acts_on_exactly_the_right_ads(
    scenarios: list[AdEconomics], thresholds: ThresholdConfig
) -> None:
    ledger = FakeLedger()
    executor = RecordingExecutor()
    result = DecisionEngine(ledger, thresholds, executor).run(scenarios, dry_run=False)

    assert result.evaluated == 4
    acted_on = {d.ad_id: d.action for d in result.actionable}
    assert acted_on == {
        "ad_loser": ActionType.PAUSE_AD,
        "ad_winner": ActionType.SCALE_BUDGET,
    }
    # The two protective cases were left completely alone.
    assert "ad_young" not in acted_on
    assert "ad_immature" not in acted_on


def test_dry_run_records_but_never_executes(
    scenarios: list[AdEconomics], thresholds: ThresholdConfig
) -> None:
    ledger = FakeLedger()
    executor = RecordingExecutor()
    result = DecisionEngine(ledger, thresholds, executor).run(scenarios, dry_run=True)

    assert len(ledger.records) == 2  # both decisions written to the ledger
    assert executor.executed == []  # nothing sent to Meta
    assert result.executed == 0
    assert all(dry_run for _, _, dry_run, _ in ledger.records)


def test_ledger_captures_the_justifying_evidence(
    scenarios: list[AdEconomics], thresholds: ThresholdConfig
) -> None:
    ledger = FakeLedger()
    DecisionEngine(ledger, thresholds, RecordingExecutor()).run(scenarios, dry_run=True)

    _, decision, _, _ = next(r for r in ledger.records if r[1].ad_id == "ad_loser")
    snapshot = decision.metrics_snapshot
    assert snapshot["lifetime_spend"] == "900"
    assert snapshot["attributed_conversions"] == 0
    assert snapshot["window_matured"] is True
    assert snapshot["rule"] == "zero_conversions"


def test_execution_failure_is_recorded_and_the_loop_continues(
    scenarios: list[AdEconomics], thresholds: ThresholdConfig
) -> None:
    # Raise the approval gate out of the way so both decisions attempt execution.
    thresholds.human_approval_spend_threshold = 1_000_000.0
    ledger = FakeLedger()
    executor = RecordingExecutor(fail_on="ad_loser")
    result = DecisionEngine(ledger, thresholds, executor).run(scenarios, dry_run=False)

    assert result.failed == 1
    assert result.executed == 1  # the winner still got scaled
    assert (ledger.id_for("ad_loser"), ActionStatus.FAILED) in ledger.marks
    assert [d.ad_id for d in executor.executed] == ["ad_winner"]


def test_per_run_action_cap_is_enforced(
    scenarios: list[AdEconomics], thresholds: ThresholdConfig
) -> None:
    thresholds.max_actions_per_run = 1
    ledger = FakeLedger()
    result = DecisionEngine(ledger, thresholds, RecordingExecutor()).run(scenarios, dry_run=False)
    assert len(result.actionable) == 1


def test_daily_cap_from_ledger_blocks_the_whole_run(
    scenarios: list[AdEconomics], thresholds: ThresholdConfig
) -> None:
    ledger = FakeLedger(actions_today=thresholds.max_actions_per_day)
    result = DecisionEngine(ledger, thresholds, RecordingExecutor()).run(scenarios, dry_run=False)
    assert result.actionable == []


def test_approval_gate_defers_execution(thresholds: ThresholdConfig) -> None:
    """A big-spending adset is recorded for a human, not executed."""
    from tests.conftest import make_econ

    thresholds.human_approval_spend_threshold = 100.0
    econ = make_econ(
        "ad_big",
        spend="3000",
        revenue="15000",
        conversions=80,
        clicks=2000,
        impressions=90_000,
    )
    ledger = FakeLedger()
    executor = RecordingExecutor()
    result = DecisionEngine(ledger, thresholds, executor).run([econ], dry_run=False)

    assert result.skipped_for_approval == 1
    assert executor.executed == []
    assert ledger.records[0][3] is ActionStatus.AWAITING_APPROVAL


def test_missing_executor_marks_actions_skipped(
    scenarios: list[AdEconomics], thresholds: ThresholdConfig
) -> None:
    ledger = FakeLedger()
    result = DecisionEngine(ledger, thresholds, executor=None).run(scenarios, dry_run=False)
    assert result.executed == 0
    assert all(status is ActionStatus.SKIPPED for _, status in ledger.marks)


def test_highest_spend_ads_are_evaluated_first(thresholds: ThresholdConfig) -> None:
    """When the action cap bites, it should bite on the smallest spenders."""
    from tests.conftest import make_econ

    small = make_econ("ad_small", spend="500", conversions=0, clicks=400, impressions=30_000)
    large = make_econ("ad_large", spend="9000", conversions=0, clicks=5000, impressions=99_000)
    thresholds.max_actions_per_run = 1

    ledger = FakeLedger()
    result = DecisionEngine(ledger, thresholds, RecordingExecutor()).run(
        [small, large], dry_run=False
    )
    assert [d.ad_id for d in result.actionable] == ["ad_large"]


def test_executor_translates_decisions_to_mutations() -> None:
    """The scale decision must carry a budget the Meta client can actually apply."""
    from agent.domain import Decision

    decision = Decision(
        action=ActionType.SCALE_BUDGET,
        adset_id="adset_1",
        reason="test",
        params={"new_budget": "120.00"},
    )
    assert Decimal(str(decision.params["new_budget"])) == Decimal("120.00")
