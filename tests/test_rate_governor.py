"""The rate governor: the layer standing between this agent and a banned account."""

from __future__ import annotations

import json

import httpx
import pytest

from agent.config import MetaSettings
from agent.meta.rate_governor import (
    THROTTLE_CODES,
    RateGovernor,
    RateLimitedError,
    extract_error,
    parse_usage_headers,
)


def _response(headers: dict[str, str]) -> httpx.Response:
    return httpx.Response(200, headers=headers, request=httpx.Request("POST", "https://x"))


def _bucu(call_count: int = 0, cputime: int = 0, total_time: int = 0, regain: int = 0) -> str:
    return json.dumps(
        {
            "act_123": [
                {
                    "type": "ads_management",
                    "call_count": call_count,
                    "total_cputime": cputime,
                    "total_time": total_time,
                    "estimated_time_to_regain_access": regain,
                }
            ]
        }
    )


def test_parses_business_use_case_usage_header() -> None:
    snapshot = parse_usage_headers(
        {"x-business-use-case-usage": _bucu(call_count=42, cputime=77, regain=600)}
    )
    assert snapshot.call_count_pct == 42
    assert snapshot.total_cputime_pct == 77
    assert snapshot.worst_pct == 77
    assert snapshot.estimated_time_to_regain_access == 600


def test_parses_ad_account_usage_header() -> None:
    snapshot = parse_usage_headers({"x-ad-account-usage": json.dumps({"acc_id_util_pct": 88})})
    assert snapshot.call_count_pct == 88


def test_malformed_headers_degrade_to_zero_rather_than_raising() -> None:
    """A broken header must never break a call in flight."""
    snapshot = parse_usage_headers({"x-business-use-case-usage": "not json {{{"})
    assert snapshot.worst_pct == 0.0
    assert parse_usage_headers({}).worst_pct == 0.0


def test_writes_cost_three_points_reads_one() -> None:
    settings = MetaSettings(access_tier="limited")
    governor = RateGovernor(settings)
    start = governor.remaining_points

    governor.charge(is_write=True)
    assert governor.remaining_points == start - 3

    governor.charge(is_write=False)
    assert governor.remaining_points == start - 4


def test_local_budget_exhaustion_refuses_before_sending() -> None:
    settings = MetaSettings(access_tier="limited")  # 60 points
    governor = RateGovernor(settings)

    for _ in range(20):  # 20 writes x 3 points = 60
        governor.check(is_write=True)
        governor.charge(is_write=True)

    with pytest.raises(RateLimitedError, match="local points budget exhausted"):
        governor.check(is_write=True)


def test_soft_threshold_triggers_self_throttle() -> None:
    settings = MetaSettings()
    governor = RateGovernor(settings)

    governor.observe(_response({"x-business-use-case-usage": _bucu(call_count=20)}))
    assert governor.throttle_delay() == 0.0

    governor.observe(_response({"x-business-use-case-usage": _bucu(call_count=85)}))
    assert governor.throttle_delay() > 0.0


def test_hard_threshold_refuses_the_call() -> None:
    settings = MetaSettings()
    governor = RateGovernor(settings)
    governor.observe(_response({"x-business-use-case-usage": _bucu(call_count=95, regain=900)}))

    with pytest.raises(RateLimitedError) as excinfo:
        governor.check(is_write=True)
    # Meta's own estimate is honoured rather than a guessed backoff.
    assert excinfo.value.retry_after_seconds == 900


def test_verification_sub_budget_cannot_crowd_out_writes() -> None:
    settings = MetaSettings(access_tier="limited", verification_budget_pct=5.0)
    governor = RateGovernor(settings)

    # 5% of 60 points = 3 points = three 1-point verification reads.
    for _ in range(3):
        governor.check(is_write=False, is_verification=True)
        governor.charge(is_write=False, is_verification=True)

    with pytest.raises(RateLimitedError, match="verification sub-budget"):
        governor.check(is_write=False, is_verification=True)

    # Writes are unaffected: the sub-budget is a ceiling on reads, not on the account.
    governor.check(is_write=True)


def test_full_tier_has_a_larger_bucket() -> None:
    assert MetaSettings(access_tier="limited").window_points == 60
    assert MetaSettings(access_tier="full").window_points == 9000


def test_throttle_error_codes_are_recognised() -> None:
    for code in (4, 17, 613, 80004):
        assert code in THROTTLE_CODES


def test_extract_error_pulls_code_and_retry_hint() -> None:
    code, message, retry = extract_error(
        {
            "error": {
                "code": 17,
                "message": "User request limit reached",
                "error_data": {"estimated_time_to_regain_access": 420},
            }
        }
    )
    assert (code, retry) == (17, 420)
    assert "limit reached" in message
