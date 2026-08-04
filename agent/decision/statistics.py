"""Confidence bounds for ad performance.

The point of this module: an ad with 2 conversions on 40 clicks has an observed CPA,
but that number carries almost no information. Acting on it churns budget and kills
ads that were fine. So the engine never compares an observed CPA to a threshold — it
compares the *bound* of a confidence interval to the threshold, and only acts when
even the optimistic reading still fails.

Pure standard library: no scipy dependency for what amounts to two closed forms.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

# Two-sided z-scores. Callers use these as one-sided bounds at the stated
# confidence, which is the conservative reading.
_Z_SCORES = {0.80: 1.2816, 0.85: 1.4395, 0.90: 1.6449, 0.95: 1.9600, 0.99: 2.5758}


def z_score(confidence: float) -> float:
    """Nearest tabulated z for a confidence level."""
    return _Z_SCORES[min(_Z_SCORES, key=lambda c: abs(c - confidence))]


@dataclass(frozen=True, slots=True)
class Interval:
    low: float
    high: float


def wilson_interval(successes: int, trials: int, confidence: float = 0.90) -> Interval:
    """Wilson score interval for a conversion rate.

    Preferred over the normal approximation because it stays inside [0, 1] and stays
    sane at small ``trials`` and at rates near zero — which is exactly the regime a
    struggling new ad lives in.
    """
    if trials <= 0:
        return Interval(0.0, 1.0)

    z = z_score(confidence)
    p = successes / trials
    denom = 1.0 + z**2 / trials
    center = (p + z**2 / (2 * trials)) / denom
    margin = (z * math.sqrt(p * (1 - p) / trials + z**2 / (4 * trials**2))) / denom
    return Interval(max(0.0, center - margin), min(1.0, center + margin))


def cpa_upper_bound(
    spend: Decimal, conversions: int, clicks: int, confidence: float = 0.90
) -> Decimal | None:
    """Pessimistic CPA: what this ad's cost per acquisition could plausibly be at worst.

    Derived by inverting the *lower* bound of the conversion rate — the fewest
    conversions we can reasonably expect from the clicks bought. Pausing requires
    even this optimistic-for-the-ad framing to fail.

    Returns None when there is no basis for an estimate (no clicks, or a lower bound
    of zero), which callers must treat as "insufficient evidence", never as "bad".
    """
    if clicks <= 0 or spend <= 0:
        return None

    rate_low = wilson_interval(conversions, clicks, confidence).low
    if rate_low <= 0:
        return None

    expected_conversions = Decimal(str(rate_low)) * Decimal(clicks)
    if expected_conversions <= 0:
        return None
    return spend / expected_conversions


def roas_lower_bound(
    revenue: Decimal, spend: Decimal, conversions: int, clicks: int, confidence: float = 0.90
) -> Decimal | None:
    """Pessimistic ROAS, scaled by the same conversion-rate uncertainty.

    Revenue per conversion is treated as stable; the uncertainty modelled is whether
    the conversions themselves will keep arriving at the observed rate.
    """
    if spend <= 0 or clicks <= 0:
        return None
    if conversions <= 0:
        return Decimal("0")

    observed_rate = conversions / clicks
    if observed_rate <= 0:
        return None
    rate_low = wilson_interval(conversions, clicks, confidence).low
    shrink = Decimal(str(rate_low / observed_rate))
    return (revenue / spend) * shrink


def has_sufficient_sample(
    spend: Decimal, impressions: int, target_cpa: Decimal, min_multiple: float, min_impressions: int
) -> bool:
    """Whether an ad has bought enough data to be judged at all.

    Both conditions must hold: enough money spent to have had a fair chance of
    converting, and enough impressions for delivery to have stabilised.
    """
    return spend >= target_cpa * Decimal(str(min_multiple)) and impressions >= min_impressions
