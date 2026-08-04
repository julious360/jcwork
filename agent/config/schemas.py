"""Schemas for the YAML config files (campaign, thresholds, brand guide).

These are the knobs an operator turns. Keeping them in YAML rather than env vars means
they are reviewable in a diff — a threshold change that will pause real ads should show
up in version control.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator


class CampaignConfig(BaseModel):
    """The vertical. Nothing product-specific is compiled into the agent."""

    product_category: str
    product_name: str
    value_proposition: str
    icp_description: str
    landing_page_url: str
    currency: str = "USD"

    research_subreddits: list[str] = Field(default_factory=list)
    research_queries: list[str] = Field(default_factory=list)
    competitor_pages: list[str] = Field(default_factory=list)
    youtube_channels: list[str] = Field(default_factory=list)
    podcast_feeds: list[str] = Field(default_factory=list)

    top_pain_points: int = 3


class AttributionConfig(BaseModel):
    model: str = "last_non_direct_click"
    lookback_days: int = 7
    # Revenue arrives well after spend. Any window newer than this is treated as
    # incomplete and is excluded from decisions rather than judged as failing.
    lag_hours: int = 48
    net_of_refunds: bool = True
    reporting_currency: str = "USD"


class ThresholdConfig(BaseModel):
    check_interval_hours: int = 6

    target_cpa: float
    cpa_max: float
    roas_min: float
    roas_scale: float

    # ── Guardrails ────────────────────────────────────────────────────────────
    # No pause until an ad has spent this multiple of target CPA. Without a floor,
    # a threshold check kills good ads on three clicks of noise.
    min_spend_multiple: float = 3.0
    min_impressions: int = 1000
    # Pause only when the *upper* confidence bound on CPA still breaches the limit.
    confidence_level: float = 0.90
    # Meta's learning phase is ~50 conversions/7d. Optimising inside it is noise-chasing.
    learning_phase_conversions: int = 50
    # Large budget jumps reset learning and burn spend.
    max_budget_increase_pct: float = 20.0
    scale_cooldown_hours: int = 24

    # ── Blast radius ──────────────────────────────────────────────────────────
    max_actions_per_run: int = 10
    max_actions_per_day: int = 40
    # Actions on adsets spending above this require a human to approve.
    human_approval_spend_threshold: float = 500.0
    kill_switch: bool = False

    # ── Anti-entropy ──────────────────────────────────────────────────────────
    novelty_threshold: float = 0.88
    novelty_history_size: int = 50
    exploration_pct: float = 20.0

    attribution: AttributionConfig = Field(default_factory=AttributionConfig)

    @model_validator(mode="after")
    def _check_coherent(self) -> ThresholdConfig:
        if self.cpa_max < self.target_cpa:
            raise ValueError("cpa_max must be >= target_cpa")
        if self.roas_scale < self.roas_min:
            raise ValueError("roas_scale must be >= roas_min")
        if not 0.5 <= self.confidence_level < 1.0:
            raise ValueError("confidence_level must be in [0.5, 1.0)")
        return self


class BrandColor(BaseModel):
    name: str
    hex: str


class BrandGuide(BaseModel):
    """Drives both halves of creative validation.

    The deterministic checker uses ``palette``/``max_delta_e`` and the spec fields;
    the vision model is handed ``tone``, ``logo_rules`` and ``forbidden_claims``.
    """

    palette: list[BrandColor]
    # CIE76 ΔE. ~2.3 is a "just noticeable difference"; 12 tolerates compression drift.
    max_delta_e: float = 12.0
    min_palette_coverage_pct: float = 25.0
    fonts: list[str] = Field(default_factory=list)
    tone: str = ""
    logo_rules: str = ""
    forbidden_claims: list[str] = Field(default_factory=list)

    # Meta ad spec. Checked in code — a vision model should never be asked to
    # eyeball whether an image is 1080px wide.
    allowed_aspect_ratios: list[float] = Field(default_factory=lambda: [1.0, 0.8, 0.5625])
    aspect_ratio_tolerance: float = 0.02
    min_width: int = 1080
    max_file_size_mb: float = 30.0
    max_text_coverage_pct: float = 20.0


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open() as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def load_campaign(path: Path | None = None) -> CampaignConfig:
    return CampaignConfig(**_load_yaml(path or Path(__file__).parent / "campaign.yaml"))


def load_thresholds(path: Path | None = None) -> ThresholdConfig:
    return ThresholdConfig(**_load_yaml(path or Path(__file__).parent / "thresholds.yaml"))


def load_brand_guide(path: Path | None = None) -> BrandGuide:
    return BrandGuide(**_load_yaml(path or Path(__file__).parent / "brand_guide.yaml"))
