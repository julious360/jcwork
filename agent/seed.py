"""Synthetic warehouse data for end-to-end verification.

Loads a small, deliberately-shaped dataset into ClickHouse so the whole chain —
migrations, identity spine, attribution SQL, mart refresh, decision engine — can be
exercised against a real database without touching Meta, Stripe, or a live ad account.

The four ads are the four cases the loop must get right:

| ad          | shape                                       | correct outcome |
|-------------|---------------------------------------------|-----------------|
| ad_loser    | heavy spend, zero payments, matured         | PAUSE           |
| ad_winner   | heavy spend, strong revenue, out of learning| SCALE           |
| ad_young    | trivial spend, no data                      | leave alone     |
| ad_immature | heavy spend, revenue hasn't landed yet      | leave alone     |

The last two matter most: a naive threshold check pauses both, and pausing them is
how an agent burns a working account in its first week.

Revenue is seeded through the *full* identity path — session -> contact -> Stripe
customer — rather than written straight into the mart, so a broken join shows up as
a wrong decision rather than passing silently.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from agent.logging_setup import get_logger
from agent.warehouse.client import WarehouseClient

log = get_logger(__name__)

CAMPAIGN_ID = "camp_seed_1"


@dataclass(slots=True)
class SeedAd:
    ad_id: str
    adset_id: str
    daily_budget: Decimal
    days: int
    hourly_spend: Decimal
    hourly_impressions: int
    hourly_clicks: int
    payments_per_day: int
    payment_value: Decimal
    # Offset from today for the ad's most recent activity. 0 keeps the ad inside the
    # attribution lag, so its window is immature and it must not be judged.
    end_days_ago: int = 3


SEED_ADS = [
    SeedAd(
        ad_id="ad_loser",
        adset_id="adset_loss",
        daily_budget=Decimal("100"),
        days=8,
        hourly_spend=Decimal("6.00"),
        hourly_impressions=900,
        hourly_clicks=14,
        payments_per_day=0,
        payment_value=Decimal("0"),
    ),
    SeedAd(
        ad_id="ad_winner",
        adset_id="adset_win",
        daily_budget=Decimal("200"),
        days=10,
        hourly_spend=Decimal("14.00"),
        hourly_impressions=1800,
        hourly_clicks=40,
        payments_per_day=9,
        payment_value=Decimal("420"),
    ),
    SeedAd(
        ad_id="ad_young",
        adset_id="adset_young",
        daily_budget=Decimal("50"),
        days=1,
        hourly_spend=Decimal("1.20"),
        hourly_impressions=40,
        hourly_clicks=1,
        payments_per_day=0,
        payment_value=Decimal("0"),
    ),
    SeedAd(
        ad_id="ad_immature",
        adset_id="adset_new",
        daily_budget=Decimal("150"),
        days=2,
        hourly_spend=Decimal("9.00"),
        hourly_impressions=1400,
        hourly_clicks=25,
        payments_per_day=0,
        payment_value=Decimal("0"),
        end_days_ago=0,
    ),
]

EXPECTED = {
    "ad_loser": "pause_ad",
    "ad_winner": "scale_budget",
    "ad_young": "no_op",
    "ad_immature": "no_op",
}


def _email_hash(seed: str) -> str:
    return hashlib.sha256(f"{seed}@example.test".encode()).hexdigest()


def build_rows(
    ads: list[SeedAd] | None = None, today: date | None = None
) -> dict[str, list[dict[str, Any]]]:
    """Generate every table's rows. Pure — no database contact, so it is unit-testable."""
    reference = today or date.today()
    ads = ads or SEED_ADS

    dim_ad: list[dict[str, Any]] = []
    performance: list[dict[str, Any]] = []
    sessions: list[dict[str, Any]] = []
    contacts: list[dict[str, Any]] = []
    payments: list[dict[str, Any]] = []

    for ad in ads:
        dim_ad.append(
            {
                "ad_id": ad.ad_id,
                "adset_id": ad.adset_id,
                "campaign_id": CAMPAIGN_ID,
                "ad_name": f"seed {ad.ad_id}",
                "adset_name": ad.adset_id,
                "campaign_name": "seed campaign",
                "creative_id": f"creative_{ad.ad_id}",
                "dna_id": f"dna_{ad.ad_id}",
                "concept_family_id": f"family_{ad.adset_id}",
                "is_external_dna": 1 if ad.ad_id == "ad_winner" else 0,
                "status": "ACTIVE",
                "effective_status": "ACTIVE",
                "daily_budget": ad.daily_budget,
                "created_time": datetime.now(UTC) - timedelta(days=ad.days + 5),
            }
        )

        for day_offset in range(ad.days):
            day = reference - timedelta(days=ad.end_days_ago + day_offset)

            # Spend, spread across the working day.
            for hour in range(9, 21):
                performance.append(
                    {
                        "ad_id": ad.ad_id,
                        "adset_id": ad.adset_id,
                        "campaign_id": CAMPAIGN_ID,
                        "hour": datetime(day.year, day.month, day.day, hour),
                        "impressions": ad.hourly_impressions,
                        "clicks": ad.hourly_clicks,
                        "link_clicks": ad.hourly_clicks,
                        "spend": ad.hourly_spend,
                        "currency": "USD",
                        "platform_conversions": ad.payments_per_day // 4,
                        "platform_conv_value": ad.payment_value * ad.payments_per_day // 4,
                    }
                )

            # Revenue, walked through the whole identity chain rather than faked.
            for n in range(ad.payments_per_day):
                key = f"{ad.ad_id}_{day_offset}_{n}"
                email = _email_hash(key)
                clicked_at = datetime(day.year, day.month, day.day, 12, 0)

                sessions.append(
                    {
                        "session_id": f"sess_{key}",
                        "ga_client_id": f"ga_{key}",
                        "fbclid": f"fbclid_{key}",
                        "utm_source": "facebook",
                        "utm_campaign": CAMPAIGN_ID,
                        # The ad id we stamp at publish time — the deterministic hop.
                        "utm_content": ad.ad_id,
                        "landing_page": "https://example.com/lp",
                        "email_sha256": email,
                        "started_at": clicked_at,
                    }
                )
                contacts.append(
                    {
                        "contact_id": f"contact_{key}",
                        "email_sha256": email,
                        "fbclid": f"fbclid_{key}",
                        "ga_client_id": f"ga_{key}",
                        "lifecycle_stage": "customer",
                        "created_at": clicked_at,
                    }
                )
                payments.append(
                    {
                        "payment_id": f"pay_{key}",
                        "stripe_customer": f"cus_{key}",
                        "email_sha256": email,
                        "amount_gross": ad.payment_value,
                        "amount_refunded": Decimal("0"),
                        "currency": "USD",
                        "fx_to_reporting": Decimal("1"),
                        "is_first_payment": 1,
                        # Lands a day after the click: inside the lookback, and a
                        # realistic lag between ad click and money.
                        "occurred_at": clicked_at + timedelta(days=1),
                    }
                )

    return {
        "dim_ad": dim_ad,
        "fact_ad_performance_hourly": performance,
        "fact_web_session": sessions,
        "fact_crm_contact": contacts,
        "fact_payment": payments,
    }


def load(client: WarehouseClient, truncate: bool = True) -> dict[str, int]:
    """Write the synthetic dataset into ClickHouse."""
    rows = build_rows()

    if truncate:
        for table in (*rows.keys(), "bridge_click_identity", "mart_ad_economics"):
            client.command(f"TRUNCATE TABLE IF EXISTS {table}")

    counts: dict[str, int] = {}
    for table, table_rows in rows.items():
        client.insert_rows(table, table_rows)
        counts[table] = len(table_rows)
        log.info("seed.loaded", table=table, rows=len(table_rows))

    return counts
