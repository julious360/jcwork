"""Confidence bounds — the machinery that keeps the rules off noise."""

from __future__ import annotations

from decimal import Decimal

from agent.decision.statistics import (
    cpa_upper_bound,
    has_sufficient_sample,
    roas_lower_bound,
    wilson_interval,
    z_score,
)


def test_wilson_interval_stays_in_range_on_extremes() -> None:
    for successes, trials in [(0, 10), (10, 10), (0, 1), (1, 1)]:
        interval = wilson_interval(successes, trials)
        assert 0.0 <= interval.low <= interval.high <= 1.0


def test_wilson_interval_narrows_with_more_data() -> None:
    """Same observed rate, more evidence, tighter interval."""
    thin = wilson_interval(2, 20)
    thick = wilson_interval(200, 2000)
    assert (thick.high - thick.low) < (thin.high - thin.low)


def test_wilson_interval_with_no_trials_is_maximally_uncertain() -> None:
    interval = wilson_interval(0, 0)
    assert (interval.low, interval.high) == (0.0, 1.0)


def test_cpa_upper_bound_is_pessimistic() -> None:
    """The bound must sit above the observed CPA — that is the safety margin."""
    observed = Decimal("300") / 2
    bound = cpa_upper_bound(Decimal("300"), 2, 40)
    assert bound is not None and bound > observed


def test_cpa_upper_bound_converges_toward_observed_with_volume() -> None:
    thin = cpa_upper_bound(Decimal("300"), 2, 40)
    thick = cpa_upper_bound(Decimal("30000"), 200, 4000)
    assert thin is not None and thick is not None
    observed = Decimal("150")
    assert (thick - observed) < (thin - observed)


def test_cpa_upper_bound_undefined_without_evidence() -> None:
    """No clicks or no conversions means no estimate — never a sentinel value."""
    assert cpa_upper_bound(Decimal("100"), 0, 0) is None
    assert cpa_upper_bound(Decimal("0"), 5, 100) is None
    assert cpa_upper_bound(Decimal("100"), 0, 5) is None  # lower bound collapses to 0


def test_roas_lower_bound_is_conservative() -> None:
    observed = Decimal("5000") / Decimal("1000")
    bound = roas_lower_bound(Decimal("5000"), Decimal("1000"), 20, 400)
    assert bound is not None and bound < observed


def test_roas_lower_bound_zero_conversions() -> None:
    assert roas_lower_bound(Decimal("0"), Decimal("500"), 0, 100) == Decimal("0")


def test_sample_size_floor() -> None:
    target = Decimal("60")
    assert not has_sufficient_sample(Decimal("100"), 5000, target, 3.0, 1000)  # spend short
    assert not has_sufficient_sample(Decimal("500"), 500, target, 3.0, 1000)  # impressions short
    assert has_sufficient_sample(Decimal("500"), 5000, target, 3.0, 1000)


def test_z_score_picks_nearest_tabulated_level() -> None:
    assert z_score(0.90) == 1.6449
    assert z_score(0.95) == 1.9600
    assert z_score(0.91) == 1.6449  # nearest
