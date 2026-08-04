"""Payload shape and the dry-run / idempotency safety properties."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from agent.config import Settings
from agent.domain import ActionType, Decision
from agent.meta.payloads import (
    ad_payload,
    adset_payload,
    budget_update_payload,
    campaign_payload,
    money_to_minor_units,
    status_payload,
)
from agent.meta.write_client import MetaWriteClient, _idempotency_key


def test_money_converts_to_minor_units() -> None:
    assert money_to_minor_units(Decimal("120.00")) == 12000
    assert money_to_minor_units(Decimal("0.99")) == 99


def test_new_objects_are_created_paused() -> None:
    """An agent that publishes straight to ACTIVE can spend on unreviewed creative."""
    assert campaign_payload("c")["status"] == "PAUSED"
    assert adset_payload("a", "c1", Decimal("50"))["status"] == "PAUSED"
    assert ad_payload("ad", "s1", "cr1")["status"] == "PAUSED"


def test_ad_payload_stamps_our_own_id_into_url_tags() -> None:
    """This stamp is what makes warehouse attribution possible without API reads."""
    payload = ad_payload("ad", "adset_1", "creative_1", tracking_ad_id="dna_abc123")
    assert "utm_content=dna_abc123" in payload["url_tags"]
    assert "utm_source=facebook" in payload["url_tags"]


def test_ad_payload_without_tracking_id_omits_url_tags() -> None:
    assert "url_tags" not in ad_payload("ad", "adset_1", "creative_1")


def test_status_and_budget_payloads() -> None:
    assert status_payload("PAUSED") == {"status": "PAUSED"}
    assert budget_update_payload(Decimal("144.00")) == {"daily_budget": 14400}


def test_idempotency_keys_are_stable_and_distinct() -> None:
    a = _idempotency_key("act_1", "ad_1", "pause:ad_1")
    b = _idempotency_key("act_1", "ad_1", "pause:ad_1")
    c = _idempotency_key("act_1", "ad_2", "pause:ad_2")
    assert a == b
    assert a != c
    assert a.startswith("meta_")


# ── Dry run ───────────────────────────────────────────────────────────────────


def _dry_client() -> MetaWriteClient:
    settings = Settings()
    settings.meta.dry_run = True
    return MetaWriteClient(settings=settings)


def test_dry_run_sends_nothing_and_reports_the_intended_payload() -> None:
    result = _dry_client().pause_ad("ad_123")
    assert result["dry_run"] is True
    assert result["payload"] == {"status": "PAUSED"}
    assert result["path"] == "ad_123"


def test_dry_run_covers_every_mutation() -> None:
    client = _dry_client()
    for call in (
        lambda: client.create_campaign("c"),
        lambda: client.create_adset("a", "c1", Decimal("50")),
        lambda: client.create_ad("ad", "s1", "cr1"),
        lambda: client.pause_ad("ad_1"),
        lambda: client.resume_ad("ad_1"),
        lambda: client.update_adset_budget("s1", Decimal("120")),
    ):
        assert call()["dry_run"] is True


def test_dry_run_is_the_default_setting() -> None:
    """A misconfigured deploy must spend nothing."""
    assert Settings().meta.dry_run is True


def test_execute_maps_decisions_to_the_right_mutation() -> None:
    client = _dry_client()

    paused = client.execute(Decision(action=ActionType.PAUSE_AD, ad_id="ad_9", reason="r"))
    assert paused["payload"]["status"] == "PAUSED"

    scaled = client.execute(
        Decision(
            action=ActionType.SCALE_BUDGET,
            adset_id="adset_9",
            reason="r",
            params={"new_budget": "240.00"},
        )
    )
    assert scaled["payload"]["daily_budget"] == 24000


def test_execute_rejects_unsupported_actions() -> None:
    import pytest

    client = _dry_client()
    with pytest.raises(ValueError, match="not an executable mutation"):
        client.execute(Decision(action=ActionType.NO_OP, reason="r"))
    with pytest.raises(ValueError, match="missing ad_id"):
        client.execute(Decision(action=ActionType.PAUSE_AD, reason="r"))


def test_verification_in_dry_run_never_hits_the_network() -> None:
    result: dict[str, Any] | None = _dry_client().verify_object_status("ad_1")
    assert result is not None and result["dry_run"] is True
