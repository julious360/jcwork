"""Turn ``mart_ad_economics`` into an audit, reusing the live decision rules.

The audit deliberately calls ``evaluate_ad`` rather than re-deriving thresholds. If
the report says an ad should be paused, it is because the same code path that would
pause it in production said so — which is the only reason the report is worth
anything. A second, prettier implementation of the rules would drift from the engine
within a month and quietly start selling conclusions the agent does not hold.

Two adjustments are made to the engine's context, both because an audit describes an
account rather than executing against one:

* ``kill_switch`` is forced off. A frozen agent should still produce a full report.
* Blast-radius counters start at zero for every ad, so findings are not truncated at
  ``max_actions_per_run``. The audit reports everything it sees; the agent is the
  thing that rations action.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from agent.audit.models import AuditReport, Finding, FindingCategory, to_monthly
from agent.config import ThresholdConfig
from agent.decision.guardrails import GuardrailContext
from agent.decision.rules import evaluate_ad
from agent.domain import ActionType, AdEconomics
from agent.logging_setup import get_logger

log = get_logger(__name__)

# Below this, identity resolution is too weak to call the revenue figure either way.
# Matches the spirit of the engine's own 0.5 hard floor, but set higher: the engine
# asks "may I act?", the audit asks "would I show this to a client as fact?".
DEFAULT_CONFIDENCE_FLOOR = 0.8


def build_audit(
    economics: list[AdEconomics],
    cfg: ThresholdConfig,
    *,
    window_days: int,
    client_name: str = "",
    currency: str = "USD",
    confidence_floor: float = DEFAULT_CONFIDENCE_FLOOR,
    today: date | None = None,
) -> AuditReport:
    report = AuditReport(
        client_name=client_name,
        generated_on=today or date.today(),
        window_days=window_days,
        currency=currency,
    )

    audit_cfg = cfg.model_copy(update={"kill_switch": False})
    adset_spend = _adset_spend(economics)

    for econ in sorted(economics, key=lambda e: e.lifetime_spend, reverse=True):
        report.ads_reviewed += 1
        report.total_spend += econ.spend
        report.total_revenue += econ.attributed_revenue
        report.platform_conversions += econ.platform_conversions
        report.attributed_conversions += econ.attributed_conversions

        finding = _classify(econ, audit_cfg, adset_spend, window_days, confidence_floor)
        if finding is not None:
            report.findings.append(finding)

    report.findings.sort(key=lambda f: f.monthly_impact, reverse=True)

    log.info(
        "audit.built",
        ads=report.ads_reviewed,
        findings=len(report.findings),
        monthly_opportunity=str(report.monthly_opportunity),
    )
    return report


def _classify(
    econ: AdEconomics,
    cfg: ThresholdConfig,
    adset_spend: dict[str, Decimal],
    window_days: int,
    confidence_floor: float,
) -> Finding | None:
    """At most one finding per ad, in descending order of what a buyer should fix."""
    # Checked before the rules run: an unresolved identity path makes the revenue
    # figure itself unreliable, so any verdict derived from it would be too.
    if econ.attribution_confidence < confidence_floor:
        return Finding(
            ad_id=econ.ad_id,
            category=FindingCategory.UNVERIFIED_REVENUE,
            spend=econ.spend,
            revenue=econ.attributed_revenue,
            monthly_impact=to_monthly(econ.spend, window_days),
            detail=(
                f"identity match confidence {econ.attribution_confidence:.2f} is below "
                f"{confidence_floor:.2f} — revenue for this ad cannot be confirmed or ruled out"
            ),
        )

    ctx = GuardrailContext(
        actions_this_run=0,
        actions_today=0,
        last_scale_at=None,
        adset_spend=adset_spend.get(econ.adset_id, Decimal("0")),
    )
    decision = evaluate_ad(econ, cfg, ctx)

    if decision.action is ActionType.PAUSE_AD:
        return Finding(
            ad_id=econ.ad_id,
            category=FindingCategory.WASTED_SPEND,
            spend=econ.spend,
            revenue=econ.attributed_revenue,
            monthly_impact=to_monthly(econ.spend, window_days),
            detail=decision.reason,
        )

    if decision.action is ActionType.SCALE_BUDGET:
        return Finding(
            ad_id=econ.ad_id,
            category=FindingCategory.UNDER_SCALED,
            spend=econ.spend,
            revenue=econ.attributed_revenue,
            monthly_impact=_scale_upside(econ, cfg),
            detail=decision.reason,
        )

    # Not a defect, and worth stating plainly: a client looking at a Meta dashboard
    # sees these ads as failing, because the revenue has not arrived yet.
    if not econ.window_matured and econ.spend > 0:
        return Finding(
            ad_id=econ.ad_id,
            category=FindingCategory.ATTRIBUTION_PENDING,
            spend=econ.spend,
            revenue=econ.attributed_revenue,
            monthly_impact=Decimal("0"),
            detail=(
                f"inside the {cfg.attribution.lag_hours}h attribution lag — spend is booked, "
                "revenue is still landing; judging this ad today reads as a false negative"
            ),
        )

    return None


def _scale_upside(econ: AdEconomics, cfg: ThresholdConfig) -> Decimal:
    """Net new monthly revenue from one safe budget step at the observed ROAS.

    Deliberately conservative on three counts: it takes a single capped step rather
    than compounding them, it uses the observed ROAS rather than the confidence
    bound the scale rule already cleared, and it nets out the added spend. Selling a
    number the account then fails to hit is worse than selling a smaller one.
    """
    roas = econ.roas
    if roas is None or econ.daily_budget <= 0 or roas <= 1:
        return Decimal("0")

    step = econ.daily_budget * Decimal(str(cfg.max_budget_increase_pct)) / Decimal("100")
    added_monthly_spend = step * Decimal("30")
    return (added_monthly_spend * (roas - Decimal("1"))).quantize(Decimal("0.01"))


def _adset_spend(economics: list[AdEconomics]) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = {}
    for econ in economics:
        totals[econ.adset_id] = totals.get(econ.adset_id, Decimal("0")) + econ.lifetime_spend
    return totals
