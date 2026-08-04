"""The action ledger and idempotency store.

Two jobs:

1. Record what the agent decided and why, permanently. ``--dry-run`` writes
   proposed-only rows, so the agent's judgment can be audited against real data
   before it is ever handed write credentials.
2. Make mutations exactly-once. A key is claimed *before* the API call; if the
   process dies between send and response, the retry sees the key and refuses to
   create a second ad or apply a budget increase twice.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from agent.domain import ActionStatus, ActionType, Decision
from agent.logging_setup import get_logger
from agent.ops.db import Database

log = get_logger(__name__)


@dataclass(slots=True)
class RecordedAction:
    id: int
    action_type: str
    status: str
    ad_id: str | None
    adset_id: str | None
    reason: str


class ActionLedger:
    def __init__(self, db: Database) -> None:
        self._db = db

    def record(
        self,
        run_id: uuid.UUID,
        decision: Decision,
        *,
        dry_run: bool,
        status: ActionStatus | None = None,
    ) -> int:
        resolved = status or (
            ActionStatus.AWAITING_APPROVAL if decision.requires_approval else ActionStatus.PROPOSED
        )
        with self._db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_actions
                    (run_id, action_type, status, ad_id, adset_id, reason,
                     metrics_snapshot, params, dry_run)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    str(run_id),
                    str(decision.action),
                    str(resolved),
                    decision.ad_id,
                    decision.adset_id,
                    decision.reason,
                    json.dumps(decision.metrics_snapshot, default=str),
                    json.dumps(decision.params, default=str),
                    dry_run,
                ),
            )
            row = cur.fetchone()
        return int(row["id"])  # type: ignore[index]

    def mark(
        self,
        action_id: int,
        status: ActionStatus,
        *,
        meta_response: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        with self._db.cursor() as cur:
            cur.execute(
                """
                UPDATE agent_actions
                SET status = %s,
                    meta_response = COALESCE(%s, meta_response),
                    error = COALESCE(%s, error),
                    executed_at = CASE WHEN %s IN ('executed', 'verified')
                                       THEN now() ELSE executed_at END
                WHERE id = %s
                """,
                (
                    str(status),
                    json.dumps(meta_response, default=str) if meta_response else None,
                    error,
                    str(status),
                    action_id,
                ),
            )

    def actions_today(self) -> int:
        """Executed actions in the last 24h — input to the daily blast-radius cap."""
        with self._db.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS n FROM agent_actions "
                "WHERE status IN ('executed', 'verified') "
                "  AND executed_at > now() - interval '24 hours'"
            )
            row = cur.fetchone()
        return int(row["n"])  # type: ignore[index]

    def last_scale_at(self, adset_id: str) -> Any:
        """When this adset was last scaled — enforces the scale cooldown."""
        with self._db.cursor() as cur:
            cur.execute(
                """
                SELECT max(executed_at) AS last_at FROM agent_actions
                WHERE adset_id = %s AND action_type = %s
                  AND status IN ('executed', 'verified')
                """,
                (adset_id, str(ActionType.SCALE_BUDGET)),
            )
            row = cur.fetchone()
        return row["last_at"] if row else None

    def pending_approval(self) -> list[RecordedAction]:
        with self._db.cursor() as cur:
            cur.execute(
                "SELECT id, action_type, status, ad_id, adset_id, reason "
                "FROM agent_actions WHERE status = 'awaiting_approval' ORDER BY id"
            )
            rows = cur.fetchall()
        return [
            RecordedAction(
                id=int(r["id"]),
                action_type=str(r["action_type"]),
                status=str(r["status"]),
                ad_id=r["ad_id"],
                adset_id=r["adset_id"],
                reason=str(r["reason"]),
            )
            for r in rows
        ]

    def run_summary(self, run_id: uuid.UUID) -> list[dict[str, Any]]:
        with self._db.cursor() as cur:
            cur.execute(
                "SELECT action_type, status, ad_id, adset_id, reason, metrics_snapshot "
                "FROM agent_actions WHERE run_id = %s ORDER BY id",
                (str(run_id),),
            )
            return [dict(r) for r in cur.fetchall()]


class IdempotencyStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    def claim(self, key: str, action_id: int | None = None) -> bool:
        """Try to claim a key. False means it was already used — do not send again."""
        with self._db.cursor() as cur:
            cur.execute(
                "INSERT INTO idempotency_keys (key, action_id) VALUES (%s, %s) "
                "ON CONFLICT (key) DO NOTHING RETURNING key",
                (key, action_id),
            )
            claimed = cur.fetchone() is not None
        if not claimed:
            log.warning("idempotency.replay_blocked", key=key)
        return claimed

    def store_result(self, key: str, result: dict[str, Any]) -> None:
        with self._db.cursor() as cur:
            cur.execute(
                "UPDATE idempotency_keys SET result = %s WHERE key = %s",
                (json.dumps(result, default=str), key),
            )

    def get_result(self, key: str) -> dict[str, Any] | None:
        with self._db.cursor() as cur:
            cur.execute("SELECT result FROM idempotency_keys WHERE key = %s", (key,))
            row = cur.fetchone()
        return dict(row["result"]) if row and row["result"] else None
