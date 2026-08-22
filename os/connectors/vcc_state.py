#!/usr/bin/env python3
"""Virtual Command Center state connector.

Walks the workspace and writes one JSON document the dashboard can render without
any backend: `apps/command-center/data/state.json`.

Design rules:
  * stdlib only — this must run from cron on a box with no project venv activated;
  * every source is optional. A missing database, a missing log, an absent skill
    directory each degrade to `null` and a reason, never to a traceback. The
    dashboard is a monitoring surface: it has to render when things are broken.

Usage:
    python os/connectors/vcc_state.py [--out PATH] [--print]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "apps" / "command-center" / "data" / "state.json"
LOG_DIR = ROOT / "memory" / "logs"


# ── helpers ───────────────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sh(*args: str) -> str | None:
    try:
        out = subprocess.run(
            args, cwd=ROOT, capture_output=True, text=True, timeout=10, check=False
        )
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _scalars(path: Path) -> dict[str, Any]:
    """Top-level `key: value` pairs from a YAML file.

    Uses PyYAML when importable and falls back to a line scanner, so the connector
    works outside the project venv. Only flat scalars are needed here.
    """
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore[import-not-found]

        loaded = yaml.safe_load(text)
        if isinstance(loaded, dict):
            return {k: v for k, v in loaded.items() if not isinstance(v, (dict, list))}
    except Exception:  # noqa: BLE001 - any parser problem falls through to the scanner
        pass

    out: dict[str, Any] = {}
    for line in text.splitlines():
        m = re.match(r"^([a-z_][a-z0-9_]*):\s*([^#\n]+?)\s*(?:#.*)?$", line)
        if not m:
            continue
        key, raw = m.group(1), m.group(2).strip().strip('"\'')
        if raw in ("", ">", "|"):
            continue
        if raw in ("true", "false"):
            out[key] = raw == "true"
        else:
            try:
                out[key] = float(raw) if "." in raw else int(raw)
            except ValueError:
                out[key] = raw
    return out


def _env(name: str, default: str = "") -> str:
    if name in os.environ:
        return os.environ[name]
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip()
    return default


# ── collectors ────────────────────────────────────────────────────────────────


def collect_system() -> dict[str, Any]:
    th = _scalars(ROOT / "agent" / "config" / "thresholds.yaml")
    camp = _scalars(ROOT / "agent" / "config" / "campaign.yaml")
    dry_run = _env("ADAGENT_META__DRY_RUN", "true").lower() not in ("false", "0", "no")
    return {
        "environment": _env("ADAGENT_ENVIRONMENT", "development"),
        "dry_run": dry_run,
        "kill_switch": bool(th.get("kill_switch", False)),
        "access_tier": _env("ADAGENT_META__ACCESS_TIER", "limited"),
        "product": camp.get("product_name", "—"),
        "category": camp.get("product_category", "—"),
        "thresholds": {
            "target_cpa": th.get("target_cpa"),
            "cpa_max": th.get("cpa_max"),
            "roas_min": th.get("roas_min"),
            "roas_scale": th.get("roas_scale"),
            "exploration_pct": th.get("exploration_pct"),
            "check_interval_hours": th.get("check_interval_hours"),
            "approval_threshold": th.get("human_approval_spend_threshold"),
        },
        "git": {
            "branch": _sh("git", "rev-parse", "--abbrev-ref", "HEAD") or "unknown",
            "commit": _sh("git", "log", "-1", "--pretty=%h %s") or "unknown",
            "dirty": bool(_sh("git", "status", "--porcelain")),
        },
    }


def collect_routines() -> list[dict[str, Any]]:
    """Routine health, read from the status files `common.sh` writes."""
    declared: dict[str, dict[str, str]] = {
        "daily-ads-review": {"cadence": "daily 08:00", "where": "local + cloud timer"},
        "weekly-newsletter": {"cadence": "Mon 07:00", "where": "local + cloud timer"},
        "refresh-dashboard": {"cadence": "every 15 min", "where": "local"},
    }
    out: list[dict[str, Any]] = []
    for name, meta in declared.items():
        record: dict[str, Any] = {
            "name": name,
            "cadence": meta["cadence"],
            "where": meta["where"],
            "status": "unknown",
            "at": None,
            "host": None,
            "message": "never run on this host",
        }
        status_file = LOG_DIR / f"{name}.status.json"
        if status_file.exists():
            try:
                record.update(json.loads(status_file.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError) as exc:
                record["status"] = "unknown"
                record["message"] = f"unreadable status file: {exc}"
        out.append(record)
    return out


def collect_skills() -> list[dict[str, Any]]:
    """Skill cards, parsed from each SKILL.md frontmatter."""
    skills: list[dict[str, Any]] = []
    for skill_md in sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md")):
        text = skill_md.read_text(encoding="utf-8")
        fm = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
        name = skill_md.parent.name
        description = ""
        if fm:
            for key, value in re.findall(r"^(name|description):\s*(.+)$", fm.group(1), re.M):
                if key == "name":
                    name = value.strip()
                else:
                    description = value.strip()
        refs = sorted(p.name for p in (skill_md.parent / "references").glob("*"))
        skills.append(
            {
                "name": name,
                "description": description,
                "thick": bool(refs),
                "references": refs,
                "command": f'claude -p "/{name}"',
            }
        )
    return skills


def collect_routers() -> list[dict[str, Any]]:
    routers = [{"name": "claude.md", "path": "CLAUDE.md", "role": "root router"}]
    for md in sorted((ROOT / ".claude" / "routers").glob("*.md")):
        first = md.read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip()
        routers.append(
            {
                "name": md.name,
                "path": f".claude/routers/{md.name}",
                "role": first.split("—", 1)[-1].strip() if "—" in first else first,
            }
        )
    return routers


def collect_content() -> dict[str, Any]:
    inbox = ROOT / "memory" / "inbox" / "transcripts"
    outbox = ROOT / "memory" / "outbox" / "newsletters"
    transcripts = [p for p in inbox.glob("*.md") if not p.name.endswith(".pains.md")]
    newsletters = sorted(outbox.glob("*.md"), reverse=True)
    done = {p.stem for p in newsletters}
    return {
        "transcripts": len(transcripts),
        "unprocessed": sorted(p.name for p in transcripts if p.stem not in done),
        "recent": [
            {"name": p.stem, "at": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc)
                .isoformat(timespec="seconds")}
            for p in newsletters[:5]
        ],
    }


def collect_ads() -> dict[str, Any]:
    """Ledger summary from Postgres. Absent driver or database → `available: false`."""
    dsn = _env("ADAGENT_POSTGRES__DSN")
    if not dsn:
        return {"available": False, "reason": "ADAGENT_POSTGRES__DSN not set"}
    try:
        import psycopg  # type: ignore[import-not-found]
    except ImportError:
        return {"available": False, "reason": "psycopg not installed (pip install -e '.[dev]')"}

    try:
        with psycopg.connect(dsn, connect_timeout=5) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, count(*) FROM agent_actions
                WHERE created_at > now() - interval '7 days' GROUP BY status
                """
            )
            by_status = {row[0]: int(row[1]) for row in cur.fetchall()}

            cur.execute(
                """
                SELECT action_type, count(*) FROM agent_actions
                WHERE created_at > now() - interval '7 days' GROUP BY action_type
                """
            )
            by_type = {row[0]: int(row[1]) for row in cur.fetchall()}

            cur.execute(
                """
                SELECT id, action_type, ad_id, reason, created_at
                FROM agent_actions WHERE status = 'awaiting_approval'
                ORDER BY created_at DESC LIMIT 10
                """
            )
            approvals = [
                {
                    "id": row[0],
                    "action": row[1],
                    "ad_id": row[2],
                    "reason": row[3],
                    "at": row[4].isoformat(timespec="seconds"),
                    "command": f"adagent approve {row[0]}",
                }
                for row in cur.fetchall()
            ]

            cur.execute(
                """
                SELECT id, action_type, status, ad_id, reason, created_at
                FROM agent_actions ORDER BY created_at DESC LIMIT 12
                """
            )
            recent = [
                {
                    "id": row[0],
                    "action": row[1],
                    "status": row[2],
                    "ad_id": row[3],
                    "reason": row[4],
                    "at": row[5].isoformat(timespec="seconds"),
                }
                for row in cur.fetchall()
            ]

            cur.execute("SELECT status, count(*) FROM jobs GROUP BY status")
            jobs = {row[0]: int(row[1]) for row in cur.fetchall()}
    except Exception as exc:  # noqa: BLE001 - the dashboard must render when the DB is down
        return {"available": False, "reason": f"{type(exc).__name__}: {exc}"}

    return {
        "available": True,
        "window_days": 7,
        "by_status": by_status,
        "by_type": by_type,
        "approvals": approvals,
        "recent": recent,
        "jobs": jobs,
    }


def build_state() -> dict[str, Any]:
    return {
        "generated_at": _now(),
        "workspace": str(ROOT),
        "system": collect_system(),
        "routers": collect_routers(),
        "skills": collect_skills(),
        "routines": collect_routines(),
        "content": collect_content(),
        "ads": collect_ads(),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Build Virtual Command Center state.json")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--print", action="store_true", dest="echo", help="also print to stdout")
    args = ap.parse_args()

    state = build_state()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    tmp.replace(args.out)  # atomic: the dashboard never reads a half-written file

    if args.echo:
        json.dump(state, sys.stdout, indent=2)
        print()
    ads = state["ads"]
    print(
        f"wrote {os.path.relpath(args.out, ROOT)} — "
        f"{len(state['skills'])} skills, {len(state['routines'])} routines, "
        f"ledger: {'live' if ads['available'] else ads['reason']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
