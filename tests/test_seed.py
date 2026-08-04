"""The seed dataset's shape, verified without a database.

``adagent seed`` + ``adagent verify`` only prove anything if the synthetic data
genuinely has the shape it claims. If the "loser" quietly had revenue, or the
"immature" ad's spend landed outside the attribution lag, verify would pass while
testing nothing.

These tests pin that shape. Row generation is pure, so all of it runs offline.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import cast

import pytest

from agent.config import load_thresholds
from agent.decision.guardrails import GuardrailContext
from agent.decision.rules import evaluate_ad
from agent.domain import ActionType, AdEconomics
from agent.seed import EXPECTED, SEED_ADS, build_rows

TODAY = date(2026, 8, 1)


@pytest.fixture
def rows() -> dict[str, list[dict[str, object]]]:
    return build_rows(today=TODAY)


def test_every_expected_scenario_has_seed_data(rows: dict[str, list[dict[str, object]]]) -> None:
    seeded = {ad["ad_id"] for ad in rows["dim_ad"]}
    assert seeded == set(EXPECTED)


def test_loser_spends_past_the_sample_floor_with_zero_revenue(
    rows: dict[str, list[dict[str, object]]],
) -> None:
    """It must be pausable on evidence, not merely unprofitable on thin data."""
    spend = sum(r["spend"] for r in rows["fact_ad_performance_hourly"] if r["ad_id"] == "ad_loser")
    cfg = load_thresholds()
    floor = cfg.target_cpa * cfg.min_spend_multiple

    assert float(spend) > floor, f"loser spend {spend} must exceed the {floor} sample floor"
    assert not [p for p in rows["fact_payment"] if "ad_loser" in str(p["payment_id"])]


def test_winner_clears_the_learning_phase_and_the_scale_benchmark(
    rows: dict[str, list[dict[str, object]]],
) -> None:
    cfg = load_thresholds()
    spend = sum(r["spend"] for r in rows["fact_ad_performance_hourly"] if r["ad_id"] == "ad_winner")
    payments = [p for p in rows["fact_payment"] if "ad_winner" in str(p["payment_id"])]
    revenue = sum(p["amount_gross"] for p in payments)

    assert len(payments) >= cfg.learning_phase_conversions, "winner must exit the learning phase"
    assert float(revenue) / float(spend) > cfg.roas_scale, "winner must beat the scale benchmark"


def test_young_ad_stays_below_the_sample_floor(
    rows: dict[str, list[dict[str, object]]],
) -> None:
    """If it crossed the floor it would be legitimately pausable, testing nothing."""
    cfg = load_thresholds()
    spend = sum(r["spend"] for r in rows["fact_ad_performance_hourly"] if r["ad_id"] == "ad_young")
    assert float(spend) < cfg.target_cpa * cfg.min_spend_multiple


def test_immature_ad_spends_inside_the_attribution_lag(
    rows: dict[str, list[dict[str, object]]],
) -> None:
    """Its most recent spend must be newer than the lag, or the case is not immature."""
    cfg = load_thresholds()
    hours = [r["hour"] for r in rows["fact_ad_performance_hourly"] if r["ad_id"] == "ad_immature"]
    latest = max(hours)
    assert isinstance(latest, datetime)

    cutoff = datetime(TODAY.year, TODAY.month, TODAY.day) - timedelta(
        hours=cfg.attribution.lag_hours
    )
    assert latest > cutoff, "immature ad must have spend inside the attribution lag"

    # It must also have spent enough that only the maturity gate protects it —
    # otherwise the sample floor would be doing the work and the gate is untested.
    spend = sum(
        r["spend"] for r in rows["fact_ad_performance_hourly"] if r["ad_id"] == "ad_immature"
    )
    assert float(spend) > cfg.target_cpa * cfg.min_spend_multiple


def test_revenue_is_seeded_through_the_full_identity_chain(
    rows: dict[str, list[dict[str, object]]],
) -> None:
    """Every payment must be reachable from an ad via session and contact.

    Writing revenue straight into the mart would let a broken join pass unnoticed.
    """
    session_emails = {r["email_sha256"] for r in rows["fact_web_session"]}
    contact_emails = {r["email_sha256"] for r in rows["fact_crm_contact"]}

    for payment in rows["fact_payment"]:
        assert payment["email_sha256"] in session_emails
        assert payment["email_sha256"] in contact_emails


def test_sessions_carry_the_stamped_ad_id(rows: dict[str, list[dict[str, object]]]) -> None:
    """utm_content is the deterministic ad -> session hop the attribution relies on."""
    seeded = {ad["ad_id"] for ad in rows["dim_ad"]}
    for session in rows["fact_web_session"]:
        assert session["utm_content"] in seeded


def test_payments_fall_inside_the_attribution_lookback(
    rows: dict[str, list[dict[str, object]]],
) -> None:
    cfg = load_thresholds()
    by_email = {r["email_sha256"]: r["started_at"] for r in rows["fact_web_session"]}

    for payment in rows["fact_payment"]:
        clicked = by_email[payment["email_sha256"]]
        assert isinstance(clicked, datetime)
        paid = payment["occurred_at"]
        assert isinstance(paid, datetime)
        assert clicked <= paid < clicked + timedelta(days=cfg.attribution.lookback_days)


def test_budgets_are_present_so_scaling_can_be_computed(
    rows: dict[str, list[dict[str, object]]],
) -> None:
    """A scale decision needs a current budget; zero would silently suppress it."""
    for ad in rows["dim_ad"]:
        assert float(ad["daily_budget"]) > 0  # type: ignore[arg-type]


def test_seed_ads_and_expectations_stay_in_sync() -> None:
    assert {ad.ad_id for ad in SEED_ADS} == set(EXPECTED)


# ── The seed data actually produces the expected decisions ────────────────────


def _aggregate(rows: dict[str, list[dict[str, object]]]) -> list[AdEconomics]:
    """Roll the seed rows up the way ``REFRESH_MART_SQL`` is specified to.

    Deliberately a separate implementation. This test asserts the *dataset* drives
    the right decisions; ``adagent verify`` then asserts the SQL reaches the same
    answer against a real ClickHouse. If the two disagree, the SQL is wrong — which
    is exactly the failure this split is designed to expose.
    """
    cfg = load_thresholds()
    lag_cutoff = datetime(TODAY.year, TODAY.month, TODAY.day) - timedelta(
        hours=cfg.attribution.lag_hours
    )
    budgets = {str(a["ad_id"]): Decimal(str(a["daily_budget"])) for a in rows["dim_ad"]}
    adsets = {str(a["ad_id"]): str(a["adset_id"]) for a in rows["dim_ad"]}

    # ad_id -> the click date each payment is credited back to.
    session_ad = {str(s["email_sha256"]): str(s["utm_content"]) for s in rows["fact_web_session"]}
    revenue: dict[str, Decimal] = {}
    conversions: dict[str, int] = {}
    for payment in rows["fact_payment"]:
        ad_id = session_ad[str(payment["email_sha256"])]
        revenue[ad_id] = revenue.get(ad_id, Decimal("0")) + Decimal(str(payment["amount_gross"]))
        conversions[ad_id] = conversions.get(ad_id, 0) + 1

    results: list[AdEconomics] = []
    for ad_id in budgets:
        perf = [r for r in rows["fact_ad_performance_hourly"] if r["ad_id"] == ad_id]
        latest = max(cast(datetime, r["hour"]) for r in perf)
        matured = latest <= lag_cutoff

        spend = sum((Decimal(str(r["spend"])) for r in perf), Decimal("0"))
        clicks = sum(int(cast(int, r["clicks"])) for r in perf)
        impressions = sum(int(cast(int, r["impressions"])) for r in perf)

        results.append(
            AdEconomics(
                ad_id=ad_id,
                adset_id=adsets[ad_id],
                campaign_id="camp_seed_1",
                day=latest.date(),
                impressions=impressions,
                clicks=clicks,
                spend=spend,
                attributed_conversions=conversions.get(ad_id, 0),
                attributed_revenue=revenue.get(ad_id, Decimal("0")),
                lifetime_spend=spend,
                lifetime_conversions=conversions.get(ad_id, 0),
                lifetime_impressions=impressions,
                daily_budget=budgets[ad_id],
                window_matured=matured,
            )
        )
    return results


def test_seed_data_drives_exactly_the_expected_decisions(
    rows: dict[str, list[dict[str, object]]],
) -> None:
    """The whole point of the fixture: these four ads, these four outcomes."""
    economics = _aggregate(rows)
    cfg = load_thresholds()

    actual = {
        econ.ad_id: str(evaluate_ad(econ, cfg, GuardrailContext()).action) for econ in economics
    }
    assert actual == EXPECTED


def test_immature_ad_would_be_paused_without_the_maturity_gate(
    rows: dict[str, list[dict[str, object]]],
) -> None:
    """Proves the gate is load-bearing rather than incidentally satisfied.

    Flip window_matured to True and the same ad becomes a pause. That difference is
    the entire value of the attribution-lag guardrail.
    """
    economics = {e.ad_id: e for e in _aggregate(rows)}
    cfg = load_thresholds()
    immature = economics["ad_immature"]

    assert immature.window_matured is False
    assert evaluate_ad(immature, cfg, GuardrailContext()).action is ActionType.NO_OP

    forced = immature.model_copy(update={"window_matured": True})
    assert evaluate_ad(forced, cfg, GuardrailContext()).action is ActionType.PAUSE_AD
