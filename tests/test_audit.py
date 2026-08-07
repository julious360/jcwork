"""The audit must agree with the engine, and must never overstate the number.

Two failure modes are worth guarding against specifically. The first is drift: a
report that recommends pausing an ad the agent would leave alone is worse than no
report, because it is sold as the agent's own conclusion. The second is inflation:
the headline figure is the basis of a commercial conversation, so every path that
could make it larger than the evidence supports is tested here.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from agent.audit import build_audit, render_markdown
from agent.audit.models import FindingCategory, to_monthly
from agent.config import ThresholdConfig
from agent.decision.guardrails import GuardrailContext
from agent.decision.rules import evaluate_ad
from agent.domain import ActionType, AdEconomics
from tests.conftest import make_econ


def _audit(economics: list[AdEconomics], cfg: ThresholdConfig, days: int = 30):
    return build_audit(economics, cfg, window_days=days, today=date(2026, 8, 7))


# ── Classification ────────────────────────────────────────────────────────────


def test_clear_loser_is_reported_as_wasted_spend(clear_loser, thresholds) -> None:
    report = _audit([clear_loser], thresholds)

    assert [f.category for f in report.findings] == [FindingCategory.WASTED_SPEND]
    assert report.monthly_waste == to_monthly(clear_loser.spend, 30)


def test_clear_winner_is_reported_as_under_scaled(clear_winner, thresholds) -> None:
    report = _audit([clear_winner], thresholds)

    assert [f.category for f in report.findings] == [FindingCategory.UNDER_SCALED]
    assert report.monthly_scale_upside > 0


def test_under_sampled_ad_produces_no_finding(under_sampled, thresholds) -> None:
    """Below the sample floor there is nothing to sell and nothing to claim."""
    assert _audit([under_sampled], thresholds).findings == []


def test_immature_window_is_reported_as_pending_not_waste(immature_window, thresholds) -> None:
    report = _audit([immature_window], thresholds)

    assert [f.category for f in report.findings] == [FindingCategory.ATTRIBUTION_PENDING]
    assert report.monthly_waste == Decimal("0")
    # Pending ads must never inflate the headline: the spend is real, the verdict isn't.
    assert report.monthly_opportunity == Decimal("0")


def test_low_confidence_ad_is_unverified_rather_than_judged(thresholds) -> None:
    """A losing-looking ad we cannot trace is a blind spot, not a confirmed loss."""
    econ = make_econ(
        "ad_murky", spend="900", conversions=0, clicks=800, impressions=50_000, confidence=0.4
    )

    report = _audit([econ], thresholds)

    assert [f.category for f in report.findings] == [FindingCategory.UNVERIFIED_REVENUE]
    assert report.monthly_waste == Decimal("0")
    assert report.monthly_unverified == to_monthly(econ.spend, 30)


# ── Agreement with the engine ─────────────────────────────────────────────────


def test_every_waste_and_scale_finding_matches_the_engines_own_verdict(
    clear_loser, clear_winner, under_sampled, immature_window, thresholds
) -> None:
    """The report's authority rests entirely on this: same rules, same answers."""
    economics = [clear_loser, clear_winner, under_sampled, immature_window]
    report = _audit(economics, thresholds)
    by_id = {e.ad_id: e for e in economics}

    expected = {
        FindingCategory.WASTED_SPEND: ActionType.PAUSE_AD,
        FindingCategory.UNDER_SCALED: ActionType.SCALE_BUDGET,
    }
    checked = 0
    for finding in report.findings:
        if finding.category not in expected:
            continue
        decision = evaluate_ad(by_id[finding.ad_id], thresholds, GuardrailContext())
        assert decision.action is expected[finding.category]
        checked += 1

    assert checked == 2


def test_kill_switch_does_not_suppress_findings(clear_loser, thresholds) -> None:
    """A frozen agent still needs to be able to explain what it would have done."""
    frozen = thresholds.model_copy(update={"kill_switch": True})

    assert _audit([clear_loser], frozen).wasted

    # And the caller's config is left untouched.
    assert frozen.kill_switch is True


def test_findings_are_not_truncated_by_the_per_run_action_cap(thresholds) -> None:
    """The agent rations action; the audit reports everything it sees."""
    capped = thresholds.model_copy(update={"max_actions_per_run": 2})
    losers = [
        make_econ(f"ad_loss_{i}", spend="900", conversions=0, clicks=800, impressions=50_000)
        for i in range(6)
    ]

    assert len(_audit(losers, capped).wasted) == 6


# ── Headline arithmetic ───────────────────────────────────────────────────────


def test_totals_and_blended_metrics(clear_loser, clear_winner, thresholds) -> None:
    report = _audit([clear_loser, clear_winner], thresholds)

    assert report.ads_reviewed == 2
    assert report.total_spend == Decimal("3900")
    assert report.total_revenue == Decimal("15000")
    assert report.blended_roas is not None
    assert round(report.blended_roas, 2) == Decimal("3.85")
    assert report.blended_cpa == Decimal("3900") / 80


def test_attribution_gap_reports_only_unmatched_platform_conversions(thresholds) -> None:
    econ = make_econ(
        "ad_gap", spend="3000", revenue="9000", conversions=40, clicks=2000, impressions=90_000
    )
    econ.platform_conversions = 100

    report = _audit([econ], thresholds)

    assert report.attribution_gap_pct == Decimal("60")


def test_attribution_gap_never_goes_negative(thresholds) -> None:
    """Warehouse joins can out-count the platform; that is not a negative gap."""
    econ = make_econ(
        "ad_over", spend="3000", revenue="9000", conversions=80, clicks=2000, impressions=90_000
    )
    econ.platform_conversions = 40

    assert _audit([econ], thresholds).attribution_gap_pct == Decimal("0")


def test_monthly_normalisation_makes_windows_comparable(clear_loser, thresholds) -> None:
    """A 15-day window and a 30-day window of the same daily burn agree on run rate."""
    fortnight = _audit([clear_loser], thresholds, days=15)
    month = _audit([clear_loser], thresholds, days=30)

    assert fortnight.monthly_waste == month.monthly_waste * 2


def test_scale_upside_is_net_of_the_added_spend(clear_winner, thresholds) -> None:
    """One capped step at the observed ROAS, minus what the step costs."""
    report = _audit([clear_winner], thresholds)

    step = clear_winner.daily_budget * Decimal("20") / Decimal("100")
    roas = clear_winner.attributed_revenue / clear_winner.spend
    assert report.monthly_scale_upside == (step * 30 * (roas - 1)).quantize(Decimal("0.01"))


def test_scale_upside_is_zero_without_a_known_budget(thresholds) -> None:
    econ = make_econ(
        "ad_nobudget",
        spend="3000",
        revenue="15000",
        conversions=80,
        clicks=2000,
        impressions=90_000,
        daily_budget="0",
    )

    report = _audit([econ], thresholds)

    assert report.under_scaled == []
    assert report.monthly_scale_upside == Decimal("0")


def test_empty_account_produces_a_zeroed_report(thresholds) -> None:
    report = _audit([], thresholds)

    assert report.ads_reviewed == 0
    assert report.monthly_opportunity == Decimal("0")
    assert report.blended_roas is None
    assert report.attribution_gap_pct is None


# ── Rendering ─────────────────────────────────────────────────────────────────


def test_rendered_report_leads_with_the_money(clear_loser, clear_winner, thresholds) -> None:
    report = build_audit(
        [clear_loser, clear_winner],
        thresholds,
        window_days=30,
        client_name="Northwind Coffee",
        today=date(2026, 8, 7),
    )

    markdown = render_markdown(report)

    assert markdown.startswith("# Paid acquisition audit — Northwind Coffee")
    assert "## What this is worth" in markdown
    assert f"${report.monthly_opportunity:,.0f}" in markdown
    assert "`ad_loser`" in markdown and "`ad_winner`" in markdown
    # The method has to be present, but after the number.
    assert markdown.index("## What this is worth") < markdown.index("How these numbers")


def test_rendered_report_is_honest_about_an_empty_account(thresholds) -> None:
    markdown = render_markdown(_audit([], thresholds))

    assert "No recoverable monthly opportunity" in markdown
    assert "What this audit does not tell you" in markdown


def test_rendered_report_flags_unmeasurable_spend_as_a_limit(thresholds) -> None:
    econ = make_econ("ad_murky", spend="900", clicks=800, impressions=50_000, confidence=0.4)

    markdown = render_markdown(_audit([econ], thresholds))

    assert "Spend you cannot currently measure" in markdown
    assert "lower bound on what is knowable" in markdown


def test_currency_follows_the_campaign(clear_loser, thresholds) -> None:
    report = build_audit(
        [clear_loser], thresholds, window_days=30, currency="EUR", today=date(2026, 8, 7)
    )

    assert "€" in render_markdown(report)
