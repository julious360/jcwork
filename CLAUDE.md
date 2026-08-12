# adagent — working notes for AI assistants

Autonomous, self-optimizing Facebook Ads agent. Read `README.md` first for the
architecture and safety posture. This file is the terse, session-to-session reference:
commands, conventions, and the constraints that are enforced by the build rather than
by memory.

## Commands

```bash
pip install -e ".[dev]"           # editable install, dev deps (ruff, mypy, pytest, sqlglot)
python3 -m ruff check agent tests    # lint
python3 -m ruff format agent tests   # format
python3 -m mypy agent                # type check (tests/ is not type-checked)
python3 -m pytest -v                 # full suite, offline, no credentials needed
adagent doctor                    # which integrations are live vs mocked
```

**Always invoke ruff/mypy/pytest as `python3 -m <tool>`, not bare.** In this dev
container, `uv tool install` has put isolated, dependency-free copies of `pytest`,
`mypy`, and `ruff` on `PATH` ahead of the ones `pip install -e ".[dev]"` puts in
`python3`'s own site-packages (`which pytest` resolves to
`~/.local/share/uv/tools/pytest/...`, an environment with no access to this project's
dependencies). Bare `pytest`/`mypy` fail there — `mypy` throws stub/version-drift errors
from a newer, unrelated mypy, and `pytest` can't even import `agent`'s dependencies.
`python3 -m ruff` happens to also pass bare, since ruff doesn't need to import project
code — but use `python3 -m` for all three uniformly rather than relying on that
coincidence. This is a container-local `PATH` artifact; it does not affect
`.github/workflows/ci.yml`, which runs on a clean GitHub-hosted runner with no `uv tool`
shadowing, so CI keeps the bare command names.

CI runs lint → format-check → mypy → pytest, in that order, as a matrix across Python
3.11 and 3.12 (matching `requires-python = ">=3.11"` and `[tool.mypy] python_version =
"3.11"`). Run the same four locally before pushing — with `python3 -m` — don't rely on
CI to find what `ruff check --fix` would have caught in a second.

## Trigger phrase: "verify work now"

When the user says this (or a close variant — "run eod", "run the daily verification",
"check today's work"), run the end-of-day auto-fix + digest pass immediately:

```bash
node toolkit/uikit/eod.mjs .
```

This auto-fixes small, safe, reversible issues (ruff lint/format here; version-stamp
sync, drifted `*-data.js` regeneration, and orphaned-asset removal for any subdirectory
with its own `VERSION` file) as its own local commit, and writes a digest to
`toolkit/reports/YYYY-MM-DD.md`. Everything requiring judgment — contrast, visual diffs,
mypy errors, broken references with no obvious fix — goes to the digest's "Needs you"
section and is never auto-changed; don't try to fix those yourself either, that's this
tool's deliberate scope boundary (see the comments at the top of `eod.mjs`), not an
oversight.

**Never `git push` as part of this.** Every commit `eod.mjs` makes must stay local —
that's a deliberate decision by the repo owner (nothing reaches the remote without his
review; he can revert or push any single commit himself later), not a step to "finish"
by pushing. Report back briefly: what got auto-fixed and what's in "Needs you". A clean
run deserves a one-line reply, not a full report.

This is documented here rather than only in a skill because this session found the
live `~/.claude/skills` directory can silently reorganize or drop a newly-created skill
mid-session (an external sync process moved a fresh skill to `.trash` without any
action from this session) — `CLAUDE.md`, read at the start of every session in this
repo, doesn't have that failure mode.

## Architecture, in one pass

- **Provider interfaces everywhere** (`agent/research/providers.py`,
  `agent/creative/providers.py`, `agent/warehouse/client.py`). Every external system —
  LLMs, the warehouse, Meta — is behind an interface with a mock implementation, which is
  why the full decision path, rate governor, and brand validation all run offline with
  zero credentials (`tests/conftest.py`). New integrations follow this pattern; don't
  reach for a concrete client where an interface already exists.
- **Config lives in three YAML files** (`agent/config/{campaign,thresholds,brand_guide}.yaml`),
  not in code, specifically so a threshold change that will pause real ads shows up in a
  diff. Nothing product-specific is compiled in — the vertical is `campaign.yaml`, the
  agent is everything else.
- **The Meta client is write-only, and the build enforces it, not the docs.**
  `agent/meta/write_client.py` has no read methods except one bounded exception
  (`verify_object_status` — status fields only, capped sub-budget). Performance data comes
  from ClickHouse; Meta's Marketing API is points-metered and polling `/insights` is the
  standard way to get an account throttled. `tests/test_meta_write_only.py` enforces this
  four ways: the public method set must equal an explicit allowlist, no method name may
  contain a read-shaped fragment (`insight`, `report`, `fetch`, `list_`, `stats`, …), no
  string literal in the module's *executable code* (AST-parsed, docstrings excluded) may
  contain `/insights`, and the one read path's field list is asserted to exclude `spend`,
  `impressions`, `clicks`, `actions`. **Adding a read path here means extending this test
  deliberately, not routing around it.**
  - This is the pattern worth reusing: a real architectural rule enforced by a test that
    reads the source rather than trusting a convention. When you add a constraint worth
    stating here, ask whether it can be a test like this one instead of a sentence.
- **New Meta entities are always created PAUSED** (`agent/meta/payloads.py`) — an agent
  that publishes straight to ACTIVE is one bug away from live spend.
- **`dry_run` defaults to `True`** (`agent/config/settings.py`). In dry-run every decision
  is still written to `agent_actions` with the metrics that justified it — the ledger is
  the product. Never flip this default; changing it is a config change in a diff, not a
  code change.
- **Idempotency keys are claimed before the request is sent** (`agent/meta/write_client.py:_write`),
  so a retry after a timeout replays instead of duplicating.

## Conventions

- Line length 100, `ruff` rule set `E,F,I,N,UP,B,SIM,RUF` (see `pyproject.toml`), `mypy
  --disallow-untyped-defs` on `agent/` — every function signature is typed, no exceptions.
- Docstrings explain *why*, not what — see `agent/decision/rules.py` (ordering: guardrails
  before confidence bounds before thresholds — reversing it pauses everything in week one)
  and `agent/meta/write_client.py` (the write-only constraint, spelled out once at module
  level rather than repeated per method).
- Tests are offline-first. `tests/conftest.py` fixtures build real config objects with
  no I/O; new tests should not require ClickHouse/Postgres/network unless they're
  specifically testing that integration.

## Commit discipline

One logical slice per commit — a rule change, a new provider, a test. Not one commit per
feature. The existing history (`259e92b`, ~7,400 lines / 49 files in one commit) is the
example to not repeat: it's unreviewable and unbisectable. If a change touches more than
one concern, split it before committing, the same way the config split already separates
"what to sell" from "how to decide."
