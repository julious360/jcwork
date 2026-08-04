"""The rules themselves: pause a loser, scale a winner, otherwise do nothing.

Reading order matters here. Each rule first asks whether it is *entitled* to act
(guardrails), then whether the evidence is strong enough (confidence bounds), and
only then whether the threshold is breached. Reversing that order is what produces
an agent that pauses everything in week one.
"""

from __future__ import annotations

from decimal import Decimal

from agent.config import ThresholdConfig
from agent.decision.guardrails import (
    GuardrailContext,
    capped_budget,
    check_pause,
    check_scale,
)
from agent.decision.statistics import cpa_upper_bound, roas_lower_bound
from agent.domain import ActionType, AdEconomics, Decision


def _snapshot(econ: AdEconomics, extra: dict[str, object] | None = None) -> dict[str, object]:
    """The evidence, frozen. Persisted with every decision so it can be re-examined."""
    snap: dict[str, object] = {
        "ad_id": econ.ad_id,
        "day": str(econ.day),
        "spend": str(econ.spend),
        "impressions": econ.impressions,
        "clicks": econ.clicks,
        "attributed_conversions": econ.attributed_conversions,
        "attributed_revenue": str(econ.attributed_revenue),
        "observed_cpa": str(econ.cpa) if econ.cpa is not None else None,
        "observed_roas": str(econ.roas) if econ.roas is not None else None,
        "lifetime_spend": str(econ.lifetime_spend),
        "lifetime_conversions": econ.lifetime_conversions,
        "lifetime_impressions": econ.lifetime_impressions,
        "attribution_confidence": econ.attribution_confidence,
        "window_matured": econ.window_matured,
    }
    if extra:
        snap.update(extra)
    return snap


def evaluate_ad(econ: AdEconomics, cfg: ThresholdConfig, ctx: GuardrailContext) -> Decision:
    """Decide what, if anything, to do about one ad."""
    scale = _try_scale(econ, cfg, ctx)
    if scale is not None:
        return scale

    pause = _try_pause(econ, cfg, ctx)
    if pause is not None:
        return pause

    return Decision(
        action=ActionType.NO_OP,
        ad_id=econ.ad_id,
        adset_id=econ.adset_id,
        reason="within thresholds, or insufficient evidence to act",
        metrics_snapshot=_snapshot(econ),
    )


def _try_pause(econ: AdEconomics, cfg: ThresholdConfig, ctx: GuardrailContext) -> Decision | None:
    guard = check_pause(econ, cfg, ctx)
    if not guard.allowed:
        return None

    cpa_bound = cpa_upper_bound(
        econ.spend, econ.attributed_conversions, econ.clicks, cfg.confidence_level
    )
    roas_bound = roas_lower_bound(
        econ.attributed_revenue,
        econ.spend,
        econ.attributed_conversions,
        econ.clicks,
        cfg.confidence_level,
    )

    # An ad past the sample floor with zero conversions is a real signal, not noise:
    # it has had a fair, funded chance and produced nothing. cpa_upper_bound returns
    # None here (no rate to invert), so this case is handled explicitly rather than
    # falling through and letting the ad run forever.
    if econ.attributed_conversions == 0:
        return Decision(
            action=ActionType.PAUSE_AD,
            ad_id=econ.ad_id,
            adset_id=econ.adset_id,
            reason=(
                f"no attributed conversions after {econ.lifetime_spend} spend "
                f"(>{cfg.min_spend_multiple}x target CPA)"
            ),
            metrics_snapshot=_snapshot(econ, {"rule": "zero_conversions"}),
        )

    # Pause only when the *optimistic* reading still breaches the limit.
    if cpa_bound is not None and cpa_bound > Decimal(str(cfg.cpa_max)):
        return Decision(
            action=ActionType.PAUSE_AD,
            ad_id=econ.ad_id,
            adset_id=econ.adset_id,
            reason=(
                f"CPA upper bound {cpa_bound:.2f} exceeds max {cfg.cpa_max:.2f} "
                f"at {cfg.confidence_level:.0%} confidence"
            ),
            metrics_snapshot=_snapshot(
                econ, {"rule": "cpa_breach", "cpa_upper_bound": str(cpa_bound)}
            ),
        )

    if roas_bound is not None and roas_bound < Decimal(str(cfg.roas_min)):
        return Decision(
            action=ActionType.PAUSE_AD,
            ad_id=econ.ad_id,
            adset_id=econ.adset_id,
            reason=(
                f"ROAS lower bound {roas_bound:.2f} below min {cfg.roas_min:.2f} "
                f"at {cfg.confidence_level:.0%} confidence"
            ),
            metrics_snapshot=_snapshot(
                econ, {"rule": "roas_breach", "roas_lower_bound": str(roas_bound)}
            ),
        )

    return None


def _try_scale(econ: AdEconomics, cfg: ThresholdConfig, ctx: GuardrailContext) -> Decision | None:
    roas_bound = roas_lower_bound(
        econ.attributed_revenue,
        econ.spend,
        econ.attributed_conversions,
        econ.clicks,
        cfg.confidence_level,
    )
    # Symmetrically to pausing: scale only when even the pessimistic reading clears
    # the bar. Scaling on a lucky day is how you buy a lot of expensive traffic.
    if roas_bound is None or roas_bound < Decimal(str(cfg.roas_scale)):
        return None

    guard = check_scale(econ, cfg, ctx)
    if not guard.allowed:
        return None

    if econ.daily_budget <= 0:
        return None

    new_budget = capped_budget(econ.daily_budget, cfg)
    return Decision(
        action=ActionType.SCALE_BUDGET,
        ad_id=econ.ad_id,
        adset_id=econ.adset_id,
        reason=(
            f"ROAS lower bound {roas_bound:.2f} exceeds scale benchmark "
            f"{cfg.roas_scale:.2f}; raising budget {econ.daily_budget} -> {new_budget} "
            f"(+{cfg.max_budget_increase_pct:.0f}% cap)"
        ),
        metrics_snapshot=_snapshot(
            econ, {"rule": "roas_scale", "roas_lower_bound": str(roas_bound)}
        ),
        params={
            "current_budget": str(econ.daily_budget),
            "new_budget": str(new_budget),
        },
        requires_approval=guard.requires_approval,
    )
