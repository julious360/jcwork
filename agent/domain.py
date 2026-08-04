"""Domain types shared across module boundaries.

Kept deliberately small: only the objects that more than one subsystem needs to agree
on live here. Module-local models stay in their own package.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field


class ActionType(StrEnum):
    PAUSE_AD = "pause_ad"
    RESUME_AD = "resume_ad"
    SCALE_BUDGET = "scale_budget"
    CREATE_AD = "create_ad"
    CREATE_ADSET = "create_adset"
    CREATE_CAMPAIGN = "create_campaign"
    NO_OP = "no_op"


class ActionStatus(StrEnum):
    PROPOSED = "proposed"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    EXECUTED = "executed"
    VERIFIED = "verified"
    FAILED = "failed"
    SKIPPED = "skipped"


class AdEconomics(BaseModel):
    """One row of ``mart_ad_economics`` — the only shape the decision engine reads.

    This is the unified ad-click-to-revenue view. ``attributed_revenue`` comes from
    Stripe via the identity bridge, not from Meta's reported conversion values.
    """

    ad_id: str
    adset_id: str
    campaign_id: str
    day: date

    impressions: int = 0
    clicks: int = 0
    spend: Decimal = Decimal("0")

    platform_conversions: int = 0
    attributed_conversions: int = 0
    attributed_revenue: Decimal = Decimal("0")

    # Rolling lifetime totals, used for the sample-size floor and learning-phase check.
    lifetime_spend: Decimal = Decimal("0")
    lifetime_conversions: int = 0
    lifetime_impressions: int = 0

    daily_budget: Decimal = Decimal("0")
    attribution_confidence: float = 1.0
    window_matured: bool = True

    @property
    def cpa(self) -> Decimal | None:
        """None when there are no conversions — an undefined CPA, not an infinite one.

        Callers must handle None explicitly rather than comparing against a sentinel;
        that distinction is what keeps zero-conversion ads inside the sample-size
        guardrail instead of being auto-paused.
        """
        if self.attributed_conversions <= 0:
            return None
        return self.spend / self.attributed_conversions

    @property
    def roas(self) -> Decimal | None:
        if self.spend <= 0:
            return None
        return self.attributed_revenue / self.spend

    @property
    def conversion_rate(self) -> float:
        if self.clicks <= 0:
            return 0.0
        return self.attributed_conversions / self.clicks


class Decision(BaseModel):
    """A proposed change plus the evidence that justifies it.

    ``metrics_snapshot`` is persisted verbatim so any past decision can be re-litigated
    against the numbers the agent actually saw, not the numbers as they look today.
    """

    action: ActionType
    ad_id: str | None = None
    adset_id: str | None = None
    reason: str
    metrics_snapshot: dict[str, object] = Field(default_factory=dict)
    params: dict[str, object] = Field(default_factory=dict)
    requires_approval: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=None))

    @property
    def is_no_op(self) -> bool:
        return self.action is ActionType.NO_OP
