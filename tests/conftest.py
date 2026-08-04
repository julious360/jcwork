"""Shared fixtures.

Everything here runs offline: no ClickHouse, no Postgres, no network, no API keys.
The decision path, the rate governor, and brand validation are all fully exercisable
without credentials, which is the point of the provider-interface design.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from agent.config import BrandGuide, CampaignConfig, ThresholdConfig, load_brand_guide
from agent.domain import AdEconomics


@pytest.fixture
def thresholds() -> ThresholdConfig:
    return ThresholdConfig(
        check_interval_hours=6,
        target_cpa=60.0,
        cpa_max=90.0,
        roas_min=1.2,
        roas_scale=2.5,
        min_spend_multiple=3.0,
        min_impressions=1000,
        confidence_level=0.90,
        learning_phase_conversions=50,
        max_budget_increase_pct=20.0,
        max_actions_per_run=10,
        max_actions_per_day=40,
        human_approval_spend_threshold=500.0,
    )


@pytest.fixture
def campaign() -> CampaignConfig:
    return CampaignConfig(
        product_category="test category",
        product_name="Test Product",
        value_proposition="Does the thing",
        icp_description="People who need the thing",
        landing_page_url="https://example.com",
    )


@pytest.fixture
def brand_guide() -> BrandGuide:
    return load_brand_guide()


def make_econ(
    ad_id: str = "ad_1",
    *,
    spend: str = "0",
    revenue: str = "0",
    conversions: int = 0,
    clicks: int = 0,
    impressions: int = 0,
    lifetime_spend: str | None = None,
    lifetime_conversions: int | None = None,
    lifetime_impressions: int | None = None,
    daily_budget: str = "100",
    matured: bool = True,
    confidence: float = 1.0,
    adset_id: str = "adset_1",
) -> AdEconomics:
    return AdEconomics(
        ad_id=ad_id,
        adset_id=adset_id,
        campaign_id="camp_1",
        day=date(2026, 8, 1),
        impressions=impressions,
        clicks=clicks,
        spend=Decimal(spend),
        attributed_conversions=conversions,
        attributed_revenue=Decimal(revenue),
        lifetime_spend=Decimal(lifetime_spend if lifetime_spend is not None else spend),
        lifetime_conversions=(
            lifetime_conversions if lifetime_conversions is not None else conversions
        ),
        lifetime_impressions=(
            lifetime_impressions if lifetime_impressions is not None else impressions
        ),
        daily_budget=Decimal(daily_budget),
        attribution_confidence=confidence,
        window_matured=matured,
    )


# ── The four scenarios the loop must get right ────────────────────────────────


@pytest.fixture
def clear_loser() -> AdEconomics:
    """Well past the spend floor, zero conversions. Must be paused."""
    return make_econ("ad_loser", spend="900", conversions=0, clicks=800, impressions=50_000)


@pytest.fixture
def clear_winner() -> AdEconomics:
    """Strong ROAS, out of the learning phase. Must be scaled."""
    return make_econ(
        "ad_winner",
        spend="3000",
        revenue="15000",
        conversions=80,
        clicks=2000,
        impressions=90_000,
        adset_id="adset_win",
    )


@pytest.fixture
def under_sampled() -> AdEconomics:
    """Terrible numbers, but on almost no data. Must be left alone."""
    return make_econ("ad_young", spend="50", conversions=0, clicks=10, impressions=200)


@pytest.fixture
def immature_window() -> AdEconomics:
    """Spend recorded, revenue not yet landed. Must be left alone."""
    return make_econ(
        "ad_immature",
        spend="1200",
        conversions=0,
        clicks=900,
        impressions=60_000,
        matured=False,
    )


@pytest.fixture
def artifacts_dir(tmp_path: Path) -> Path:
    path = tmp_path / "artifacts"
    path.mkdir()
    return path
