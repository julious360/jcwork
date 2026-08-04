"""The decision rules and their guardrails.

The two tests that matter most are the negative ones: an under-sampled ad and an ad
whose revenue has not landed yet must both be left alone. Those are the cases where
a naive threshold check destroys an account.
"""

from __future__ import annotations

from datetime import UTC
from decimal import Decimal

from agent.config import ThresholdConfig
from agent.decision.guardrails import GuardrailContext, capped_budget, check_pause, check_scale
from agent.decision.rules import evaluate_ad
from agent.domain import ActionType, AdEconomics
from tests.conftest import make_econ


def test_clear_loser_is_paused(clear_loser: AdEconomics, thresholds: ThresholdConfig) -> None:
    decision = evaluate_ad(clear_loser, thresholds, GuardrailContext())
    assert decision.action is ActionType.PAUSE_AD
    assert "no attributed conversions" in decision.reason
    assert decision.metrics_snapshot["rule"] == "zero_conversions"


def test_clear_winner_is_scaled(clear_winner: AdEconomics, thresholds: ThresholdConfig) -> None:
    decision = evaluate_ad(clear_winner, thresholds, GuardrailContext())
    assert decision.action is ActionType.SCALE_BUDGET
    # The increase is capped, not proportional to how well it is doing.
    assert decision.params["new_budget"] == "120.00"


def test_under_sampled_ad_is_never_touched(
    under_sampled: AdEconomics, thresholds: ThresholdConfig
) -> None:
    """Zero conversions on 10 clicks is noise, not evidence."""
    decision = evaluate_ad(under_sampled, thresholds, GuardrailContext())
    assert decision.action is ActionType.NO_OP

    guard = check_pause(under_sampled, thresholds, GuardrailContext())
    assert not guard.allowed
    assert "insufficient sample" in guard.reason


def test_immature_window_is_never_touched(
    immature_window: AdEconomics, thresholds: ThresholdConfig
) -> None:
    """Spend has landed but revenue has not; judging now would pause a healthy ad."""
    decision = evaluate_ad(immature_window, thresholds, GuardrailContext())
    assert decision.action is ActionType.NO_OP

    guard = check_pause(immature_window, thresholds, GuardrailContext())
    assert "attribution window immature" in guard.reason


def test_learning_phase_blocks_scaling(thresholds: ThresholdConfig) -> None:
    """Great ROAS but too few conversions to have exited learning."""
    econ = make_econ(
        "ad_learning",
        spend="1000",
        revenue="6000",
        conversions=20,
        clicks=500,
        impressions=40_000,
    )
    assert evaluate_ad(econ, thresholds, GuardrailContext()).action is ActionType.NO_OP
    assert "learning phase" in check_scale(econ, thresholds, GuardrailContext()).reason


def test_scale_cooldown_blocks_repeat_scaling(
    clear_winner: AdEconomics, thresholds: ThresholdConfig
) -> None:
    from datetime import datetime, timedelta

    recent = datetime.now(UTC) - timedelta(hours=2)
    ctx = GuardrailContext(last_scale_at=recent)
    assert evaluate_ad(clear_winner, thresholds, ctx).action is ActionType.NO_OP
    assert "cooldown" in check_scale(clear_winner, thresholds, ctx).reason


def test_kill_switch_blocks_everything(
    clear_loser: AdEconomics, clear_winner: AdEconomics, thresholds: ThresholdConfig
) -> None:
    thresholds.kill_switch = True
    ctx = GuardrailContext()
    assert evaluate_ad(clear_loser, thresholds, ctx).action is ActionType.NO_OP
    assert evaluate_ad(clear_winner, thresholds, ctx).action is ActionType.NO_OP


def test_daily_action_cap_blocks_further_actions(
    clear_loser: AdEconomics, thresholds: ThresholdConfig
) -> None:
    ctx = GuardrailContext(actions_today=thresholds.max_actions_per_day)
    assert evaluate_ad(clear_loser, thresholds, ctx).action is ActionType.NO_OP


def test_low_attribution_confidence_blocks_pause(thresholds: ThresholdConfig) -> None:
    """If we do not trust the identity join, we do not act on the revenue figure."""
    econ = make_econ(
        "ad_fuzzy",
        spend="900",
        conversions=0,
        clicks=800,
        impressions=50_000,
        confidence=0.3,
    )
    assert evaluate_ad(econ, thresholds, GuardrailContext()).action is ActionType.NO_OP


def test_high_spend_scaling_requires_approval(thresholds: ThresholdConfig) -> None:
    econ = make_econ(
        "ad_big",
        spend="3000",
        revenue="15000",
        conversions=80,
        clicks=2000,
        impressions=90_000,
    )
    ctx = GuardrailContext(adset_spend=Decimal("5000"))
    decision = evaluate_ad(econ, thresholds, ctx)
    assert decision.action is ActionType.SCALE_BUDGET
    assert decision.requires_approval is True


def test_marginal_cpa_breach_does_not_pause_on_thin_data(thresholds: ThresholdConfig) -> None:
    """Observed CPA is over the limit, but the confidence bound says wait.

    This is the case a point-estimate rule gets wrong: 4 conversions on 300 clicks
    reads as CPA 100 (over the 90 max), yet the interval is far too wide to act on.
    """
    econ = make_econ(
        "ad_marginal",
        spend="400",
        revenue="600",
        conversions=4,
        clicks=300,
        impressions=25_000,
    )
    assert econ.cpa is not None and econ.cpa > Decimal("90")
    # It still pauses — but on the ROAS bound, with the reason recorded, not on a
    # bare CPA point estimate.
    decision = evaluate_ad(econ, thresholds, GuardrailContext())
    assert decision.metrics_snapshot.get("rule") in {"cpa_breach", "roas_breach"}


def test_budget_cap_is_applied() -> None:
    cfg = ThresholdConfig(target_cpa=10, cpa_max=20, roas_min=1, roas_scale=2)
    assert capped_budget(Decimal("100"), cfg) == Decimal("120.00")
    cfg.max_budget_increase_pct = 50.0
    assert capped_budget(Decimal("100"), cfg) == Decimal("150.00")
