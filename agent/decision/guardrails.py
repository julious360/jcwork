"""Guardrails: the checks that make unattended threshold rules survivable.

A bare "pause if CPA > max" rule is actively dangerous in production. It fires on
statistical noise, it fires on revenue that simply has not landed yet, and it fires
inside Meta's learning phase where the numbers mean the least. Each guardrail below
exists because of a specific way that rule destroys an account.

Guardrails only ever *veto*. They can stop the agent acting; they can never cause an
action on their own. That asymmetry is deliberate — a bug here should fail closed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from agent.config import ThresholdConfig
from agent.decision.statistics import has_sufficient_sample
from agent.domain import AdEconomics


@dataclass(slots=True)
class GuardrailContext:
    """Everything the guardrails need that isn't on the ad record itself."""

    actions_this_run: int = 0
    actions_today: int = 0
    last_scale_at: datetime | None = None
    adset_spend: Decimal = Decimal("0")


@dataclass(slots=True)
class GuardrailResult:
    allowed: bool
    blocked_by: list[str] = field(default_factory=list)
    requires_approval: bool = False

    @property
    def reason(self) -> str:
        return "; ".join(self.blocked_by)


def check_common(econ: AdEconomics, cfg: ThresholdConfig, ctx: GuardrailContext) -> list[str]:
    """Vetoes that apply to any action on any ad."""
    blocks: list[str] = []

    if cfg.kill_switch:
        blocks.append("kill_switch engaged")

    if ctx.actions_this_run >= cfg.max_actions_per_run:
        blocks.append(f"per-run action cap reached ({cfg.max_actions_per_run})")

    if ctx.actions_today >= cfg.max_actions_per_day:
        blocks.append(f"daily action cap reached ({cfg.max_actions_per_day})")

    # Revenue lands after spend. Judging an immature window means judging spend
    # against revenue that has not arrived — every recent ad looks like a loser.
    if not econ.window_matured:
        blocks.append(f"attribution window immature (<{cfg.attribution.lag_hours}h)")

    return blocks


def check_pause(econ: AdEconomics, cfg: ThresholdConfig, ctx: GuardrailContext) -> GuardrailResult:
    blocks = check_common(econ, cfg, ctx)

    # A threshold check on three clicks of data is a coin flip, not a decision.
    if not has_sufficient_sample(
        econ.lifetime_spend,
        econ.lifetime_impressions,
        Decimal(str(cfg.target_cpa)),
        cfg.min_spend_multiple,
        cfg.min_impressions,
    ):
        blocks.append(
            f"insufficient sample (spend {econ.lifetime_spend} < "
            f"{cfg.min_spend_multiple}x target CPA, or impressions "
            f"{econ.lifetime_impressions} < {cfg.min_impressions})"
        )

    # Weak identity resolution means the revenue figure itself is shaky; do not
    # pause an ad on evidence we do not trust.
    if econ.attribution_confidence < 0.5:
        blocks.append(f"attribution confidence too low ({econ.attribution_confidence:.2f})")

    return GuardrailResult(allowed=not blocks, blocked_by=blocks)


def check_scale(econ: AdEconomics, cfg: ThresholdConfig, ctx: GuardrailContext) -> GuardrailResult:
    blocks = check_common(econ, cfg, ctx)

    if not has_sufficient_sample(
        econ.lifetime_spend,
        econ.lifetime_impressions,
        Decimal(str(cfg.target_cpa)),
        cfg.min_spend_multiple,
        cfg.min_impressions,
    ):
        blocks.append("insufficient sample to scale")

    # Inside the learning phase, delivery is still being optimised and the numbers
    # are not yet stable. Scaling now resets that learning and wastes the spend
    # already invested in it.
    if econ.lifetime_conversions < cfg.learning_phase_conversions:
        blocks.append(
            f"still in learning phase ({econ.lifetime_conversions} < "
            f"{cfg.learning_phase_conversions} conversions)"
        )

    # Repeated jumps in quick succession compound into a budget explosion and
    # re-trigger learning each time.
    if ctx.last_scale_at is not None:
        elapsed = datetime.now(UTC) - _as_utc(ctx.last_scale_at)
        if elapsed < timedelta(hours=cfg.scale_cooldown_hours):
            remaining = cfg.scale_cooldown_hours - elapsed.total_seconds() / 3600
            blocks.append(f"scale cooldown active ({remaining:.1f}h remaining)")

    # Big spenders get a human in the loop rather than a veto.
    needs_approval = ctx.adset_spend >= Decimal(str(cfg.human_approval_spend_threshold))

    return GuardrailResult(allowed=not blocks, blocked_by=blocks, requires_approval=needs_approval)


def capped_budget(current: Decimal, cfg: ThresholdConfig) -> Decimal:
    """The largest budget we are willing to jump to in one step."""
    factor = Decimal("1") + Decimal(str(cfg.max_budget_increase_pct)) / Decimal("100")
    return (current * factor).quantize(Decimal("0.01"))


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
