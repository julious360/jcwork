"""Request payload builders for Meta mutations.

Kept separate from the client so payload shape can be unit-tested without any
network stack, and so the client file stays small enough to audit at a glance for
the one property that matters: that it cannot read.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def money_to_minor_units(amount: Decimal) -> int:
    """Meta budgets are integers in the account's minor currency unit (cents)."""
    return int((amount * 100).quantize(Decimal("1")))


def campaign_payload(
    name: str, objective: str = "OUTCOME_SALES", status: str = "PAUSED"
) -> dict[str, Any]:
    # New objects are created PAUSED by default: an agent that publishes straight to
    # ACTIVE can spend money on a creative no human has ever seen.
    return {
        "name": name,
        "objective": objective,
        "status": status,
        "special_ad_categories": "[]",
    }


def adset_payload(
    name: str,
    campaign_id: str,
    daily_budget: Decimal,
    optimization_goal: str = "OFFSITE_CONVERSIONS",
    billing_event: str = "IMPRESSIONS",
    targeting: dict[str, Any] | None = None,
    status: str = "PAUSED",
) -> dict[str, Any]:
    return {
        "name": name,
        "campaign_id": campaign_id,
        "daily_budget": money_to_minor_units(daily_budget),
        "billing_event": billing_event,
        "optimization_goal": optimization_goal,
        "targeting": targeting or {"geo_locations": {"countries": ["US"]}},
        "status": status,
    }


def ad_payload(
    name: str,
    adset_id: str,
    creative_id: str,
    tracking_ad_id: str | None = None,
    status: str = "PAUSED",
) -> dict[str, Any]:
    """Build an ad, stamping our own identifier into the click URL.

    ``url_tags`` is what makes warehouse-side attribution possible without ever
    reading from the Marketing API: the ad id we control arrives in GA4 as
    ``utm_content``, which the identity bridge joins on. Resolving an fbclid back to
    an ad any other way would cost an API read per click.
    """
    payload: dict[str, Any] = {
        "name": name,
        "adset_id": adset_id,
        "creative": {"creative_id": creative_id},
        "status": status,
    }
    if tracking_ad_id:
        payload["url_tags"] = f"utm_source=facebook&utm_medium=paid&utm_content={tracking_ad_id}"
    return payload


def budget_update_payload(new_daily_budget: Decimal) -> dict[str, Any]:
    return {"daily_budget": money_to_minor_units(new_daily_budget)}


def status_payload(status: str) -> dict[str, Any]:
    return {"status": status}
