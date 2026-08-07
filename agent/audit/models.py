"""What a paid attribution audit produces.

The audit is a *read-only* pass over the same warehouse view the decision engine
reads, rendered for someone who is not going to run the CLI. It answers four
questions, in the order a buyer cares about them:

1. How much of last month's spend bought nothing we can trace to money?
2. Which ads are underfunded relative to what they actually returned?
3. How far apart are Meta's reported conversions and provable revenue?
4. How much spend sits behind evidence too weak to act on at all?

Nothing here decides anything or writes anywhere. The audit exists so the numbers
can be handed over before any access to the ad account is granted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum

MONTH_DAYS = Decimal("30")


class FindingCategory(StrEnum):
    """Why an ad appears in the report."""

    # Past the sample floor, matured, and failing its CPA/ROAS bound.
    WASTED_SPEND = "wasted_spend"
    # Clearing the scale benchmark on the pessimistic bound, still on a flat budget.
    UNDER_SCALED = "under_scaled"
    # Identity resolution too weak to trust the revenue figure either way.
    UNVERIFIED_REVENUE = "unverified_revenue"
    # Spend is real, revenue has not finished landing. Not a problem — a timing fact.
    ATTRIBUTION_PENDING = "attribution_pending"


@dataclass(slots=True)
class Finding:
    """One ad, one reason it is worth the reader's attention, one dollar figure."""

    ad_id: str
    category: FindingCategory
    spend: Decimal
    revenue: Decimal
    # Normalised to a 30-day run rate so findings from a 14-day and a 60-day window
    # are comparable, and so the total lines up with how a buyer budgets.
    monthly_impact: Decimal
    detail: str

    @property
    def roas(self) -> Decimal | None:
        if self.spend <= 0:
            return None
        return self.revenue / self.spend


@dataclass(slots=True)
class AuditReport:
    """The deliverable. Rendered to Markdown by ``agent.audit.render``."""

    client_name: str
    generated_on: date
    window_days: int
    currency: str

    ads_reviewed: int = 0
    total_spend: Decimal = Decimal("0")
    total_revenue: Decimal = Decimal("0")
    platform_conversions: int = 0
    attributed_conversions: int = 0

    findings: list[Finding] = field(default_factory=list)

    # ── Headline economics ────────────────────────────────────────────────────

    @property
    def blended_roas(self) -> Decimal | None:
        if self.total_spend <= 0:
            return None
        return self.total_revenue / self.total_spend

    @property
    def blended_cpa(self) -> Decimal | None:
        if self.attributed_conversions <= 0:
            return None
        return self.total_spend / self.attributed_conversions

    @property
    def attribution_gap_pct(self) -> Decimal | None:
        """Share of Meta-reported conversions that no revenue path can substantiate.

        Not fraud and not necessarily error — Meta counts view-through and modelled
        conversions that a deterministic click-to-Stripe join will never see. The
        number matters because it is the size of the gap between the dashboard the
        client optimises against and the bank account they are judged on.
        """
        if self.platform_conversions <= 0:
            return None
        unmatched = self.platform_conversions - self.attributed_conversions
        return Decimal(max(unmatched, 0)) / Decimal(self.platform_conversions) * Decimal("100")

    # ── Money, by category ────────────────────────────────────────────────────

    def _by(self, category: FindingCategory) -> list[Finding]:
        return [f for f in self.findings if f.category is category]

    def _monthly(self, category: FindingCategory) -> Decimal:
        return sum((f.monthly_impact for f in self._by(category)), Decimal("0"))

    @property
    def wasted(self) -> list[Finding]:
        return self._by(FindingCategory.WASTED_SPEND)

    @property
    def under_scaled(self) -> list[Finding]:
        return self._by(FindingCategory.UNDER_SCALED)

    @property
    def unverified(self) -> list[Finding]:
        return self._by(FindingCategory.UNVERIFIED_REVENUE)

    @property
    def pending(self) -> list[Finding]:
        return self._by(FindingCategory.ATTRIBUTION_PENDING)

    @property
    def monthly_waste(self) -> Decimal:
        """Spend on ads that are provably not returning, at a 30-day run rate."""
        return self._monthly(FindingCategory.WASTED_SPEND)

    @property
    def monthly_scale_upside(self) -> Decimal:
        """Net new monthly revenue from funding the winners to the safe cap."""
        return self._monthly(FindingCategory.UNDER_SCALED)

    @property
    def monthly_unverified(self) -> Decimal:
        """Spend whose outcome the current tracking setup cannot resolve either way."""
        return self._monthly(FindingCategory.UNVERIFIED_REVENUE)

    @property
    def monthly_opportunity(self) -> Decimal:
        """The one number the cover page leads with."""
        return self.monthly_waste + self.monthly_scale_upside


def to_monthly(amount: Decimal, window_days: int) -> Decimal:
    """Project a windowed figure to a 30-day run rate."""
    if window_days <= 0:
        return Decimal("0")
    return (amount / Decimal(window_days) * MONTH_DAYS).quantize(Decimal("0.01"))
