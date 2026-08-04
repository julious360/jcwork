"""ClickHouse access.

This is the agent's read path — all of it. Performance data is never fetched from
the Meta API; it is read here, from data Airbyte landed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import clickhouse_connect
from clickhouse_connect.driver.client import Client

from agent.config import Settings, get_settings
from agent.logging_setup import get_logger

log = get_logger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations" / "clickhouse"


class WarehouseClient:
    """Thin wrapper over clickhouse-connect with migration support."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client: Client | None = None

    @property
    def client(self) -> Client:
        if self._client is None:
            ch = self._settings.clickhouse
            self._client = clickhouse_connect.get_client(
                host=ch.host,
                port=ch.port,
                database=ch.database,
                username=ch.user,
                password=ch.password.get_secret_value(),
                secure=ch.secure,
            )
        return self._client

    def query(self, sql: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        result = self.client.query(sql, parameters=parameters or {})
        columns = result.column_names
        return [dict(zip(columns, row, strict=True)) for row in result.result_rows]

    def command(self, sql: str, parameters: dict[str, Any] | None = None) -> None:
        self.client.command(sql, parameters=parameters or {})

    def insert_rows(self, table: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        columns = list(rows[0].keys())
        data = [[row[c] for c in columns] for row in rows]
        self.client.insert(table, data, column_names=columns)

    def migrate(self, migrations_dir: Path | None = None) -> list[str]:
        """Apply .sql migrations in filename order.

        Statements are idempotent (``CREATE ... IF NOT EXISTS``), so re-running is
        safe and no migration-version table is needed for this schema's shape.
        """
        directory = migrations_dir or MIGRATIONS_DIR
        applied: list[str] = []
        for path in sorted(directory.glob("*.sql")):
            sql = path.read_text()
            for statement in _split_statements(sql):
                self.client.command(statement)
            applied.append(path.name)
            log.info("clickhouse.migration_applied", migration=path.name)
        return applied

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None


def _strip_sql_comments(sql: str) -> str:
    """Remove ``--`` comments, leaving string literals untouched.

    Done before splitting, not after: a prose comment containing a semicolon would
    otherwise tear a CREATE TABLE in half and produce two invalid statements.
    """
    out: list[str] = []
    for line in sql.splitlines():
        in_single = in_double = False
        cut = len(line)
        i = 0
        while i < len(line):
            char = line[i]
            if char == "'" and not in_double:
                in_single = not in_single
            elif char == '"' and not in_single:
                in_double = not in_double
            elif (
                char == "-"
                and not in_single
                and not in_double
                and i + 1 < len(line)
                and line[i + 1] == "-"
            ):
                cut = i
                break
            i += 1
        out.append(line[:cut].rstrip())
    return "\n".join(out)


def _split_statements(sql: str) -> list[str]:
    """Split a migration file into executable statements.

    Comments go first, then the split happens only on semicolons outside string
    literals. clickhouse-connect executes one statement per call, so getting this
    boundary right is what makes the migrations apply at all.
    """
    cleaned = _strip_sql_comments(sql)
    statements: list[str] = []
    current: list[str] = []
    in_single = in_double = False

    for char in cleaned:
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double

        if char == ";" and not in_single and not in_double:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(char)

    trailing = "".join(current).strip()
    if trailing:
        statements.append(trailing)
    return statements
