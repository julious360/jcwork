"""SQL validity: migrations and the runtime query library.

These queries only ever run against a real database, which means a syntax error
would surface at deploy time rather than in CI. Parsing them here with the correct
dialect catches that class of mistake for free.

The statement splitter is tested alongside them, because getting statement
boundaries wrong is what silently breaks a migration: a semicolon inside a prose
comment can tear a CREATE TABLE in half and yield two invalid fragments.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import sqlglot

from agent.warehouse import queries
from agent.warehouse.client import _split_statements, _strip_sql_comments

ROOT = Path(__file__).resolve().parents[1]
CLICKHOUSE_MIGRATIONS = sorted((ROOT / "migrations" / "clickhouse").glob("*.sql"))
POSTGRES_MIGRATIONS = sorted((ROOT / "migrations" / "postgres").glob("*.sql"))


def _substitute_params(sql: str) -> str:
    """Replace ClickHouse ``{name:Type}`` bindings with literals so the SQL parses."""

    def replace(match: re.Match[str]) -> str:
        kind = match.group(2).lower()
        if "date" in kind:
            return "'2026-01-01'"
        if any(k in kind for k in ("int", "float", "decimal")):
            return "1"
        return "'x'"

    return re.sub(r"\{(\w+):(\w+)\}", replace, sql)


# ── The splitter ──────────────────────────────────────────────────────────────


def test_comments_are_stripped_before_splitting() -> None:
    """A semicolon inside a comment must not end the statement."""
    sql = """
    CREATE TABLE t
    (
        a String,
        -- a prose comment; with a semicolon in it
        b UInt64
    )
    ENGINE = MergeTree ORDER BY a;
    """
    statements = _split_statements(sql)
    assert len(statements) == 1
    assert "b UInt64" in statements[0]


def test_semicolons_inside_string_literals_are_preserved() -> None:
    statements = _split_statements("SELECT 'a;b' AS x; SELECT 2")
    assert len(statements) == 2
    assert "'a;b'" in statements[0]


def test_double_hyphen_inside_a_string_is_not_a_comment() -> None:
    assert "'a--b'" in _strip_sql_comments("SELECT 'a--b' AS x")


def test_empty_and_comment_only_input_yields_no_statements() -> None:
    assert _split_statements("") == []
    assert _split_statements("-- just a comment\n-- another\n") == []


# ── Migrations ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", CLICKHOUSE_MIGRATIONS, ids=lambda p: p.name)
def test_clickhouse_migrations_parse(path: Path) -> None:
    statements = _split_statements(path.read_text())
    assert statements, f"{path.name} produced no statements"
    for statement in statements:
        sqlglot.parse_one(statement, dialect="clickhouse")


@pytest.mark.parametrize("path", POSTGRES_MIGRATIONS, ids=lambda p: p.name)
def test_postgres_migrations_parse(path: Path) -> None:
    parsed = sqlglot.parse(path.read_text(), dialect="postgres")
    assert parsed


def test_every_table_the_agent_reads_is_created_by_a_migration() -> None:
    ddl = "\n".join(p.read_text() for p in CLICKHOUSE_MIGRATIONS)
    for table in (
        "dim_ad",
        "fact_ad_performance_hourly",
        "fact_web_session",
        "fact_crm_contact",
        "fact_crm_deal",
        "fact_payment",
        "bridge_click_identity",
        "mart_ad_economics",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in ddl


def test_postgres_ops_tables_exist() -> None:
    ddl = "\n".join(p.read_text() for p in POSTGRES_MIGRATIONS)
    for table in (
        "jobs",
        "agent_actions",
        "idempotency_keys",
        "circuit_breaker",
        "creative_assets",
        "dna_pool",
        "shipped_concepts",
        "research_cache",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in ddl


# ── Runtime queries ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "sql",
    [queries.REBUILD_IDENTITY_SQL, queries.REFRESH_MART_SQL, queries.LATEST_ECONOMICS_SQL],
    ids=["rebuild_identity", "refresh_mart", "latest_economics"],
)
def test_runtime_queries_parse(sql: str) -> None:
    sqlglot.parse_one(_substitute_params(sql), dialect="clickhouse")


def test_decision_engine_reads_only_the_mart() -> None:
    """The engine's read path must not reach past mart_ad_economics."""
    assert "mart_ad_economics" in queries.LATEST_ECONOMICS_SQL
    for raw_table in ("fact_payment", "fact_web_session", "bridge_click_identity"):
        assert raw_table not in queries.LATEST_ECONOMICS_SQL


def test_mart_refresh_nets_off_refunds_and_respects_the_lookback() -> None:
    sql = queries.REFRESH_MART_SQL
    assert "amount_refunded" in sql
    assert "{lookback:UInt32}" in sql
    # The maturity gate is what stops immature revenue being judged as failure.
    assert "{lag_hours:UInt32}" in sql
    assert "window_matured" in sql


def test_latest_economics_uses_final_to_collapse_duplicates() -> None:
    """ReplacingMergeTree needs FINAL, or a re-run double-counts spend."""
    assert "FINAL" in queries.LATEST_ECONOMICS_SQL
