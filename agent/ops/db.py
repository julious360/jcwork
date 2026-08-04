"""Postgres connection handling and migrations."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from agent.config import Settings, get_settings
from agent.logging_setup import get_logger

log = get_logger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations" / "postgres"


class Database:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @property
    def dsn(self) -> str:
        return self._settings.postgres.dsn.get_secret_value()

    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection[Any]]:
        with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
            yield conn

    @contextmanager
    def cursor(self) -> Iterator[psycopg.Cursor[Any]]:
        """A cursor in its own transaction, committed on clean exit."""
        with self.connection() as conn, conn.cursor() as cur:
            yield cur
            conn.commit()

    def migrate(self, migrations_dir: Path | None = None) -> list[str]:
        directory = migrations_dir or MIGRATIONS_DIR
        applied: list[str] = []
        with self.connection() as conn:
            for path in sorted(directory.glob("*.sql")):
                with conn.cursor() as cur:
                    cur.execute(path.read_text())
                conn.commit()
                applied.append(path.name)
                log.info("postgres.migration_applied", migration=path.name)
        return applied
