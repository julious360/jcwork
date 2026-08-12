---
name: ui-verify
description: Mechanically verify a static HTML/CSS/JS site or mockup before calling it done — deterministic screenshots, visual diffing, and an audit for broken assets, offline-guarantee violations, contrast, and version-stamp mismatches. Also covers the end-of-day pass across a whole repo. Use whenever the user asks to check, verify, review, or gate a page/site/mockup, says a phrase like "verify work now" / "run the daily verification" / "run eod", or before reporting any UI change as finished.
---

# UI Verification

## Trigger phrase: "verify work now"

When the user says this (or a close variant — "run eod", "run the daily
verification", "check today's work") run the end-of-day pass immediately:

```bash
node toolkit/uikit/eod.mjs .
```

From the repo root. This is different from `gate.mjs` below — `eod.mjs` is the whole-repo
daily pass (Python lint/format plus every "site" subdirectory found), auto-fixes what's
safe as its own local commit, and writes a digest to `toolkit/reports/YYYY-MM-DD.md`.
**Never `git push` as part of this** — every commit it makes must stay local-only; that's
a deliberate decision by the repo owner (nothing reaches the remote without his review),
not a step to "finish" by pushing. Report back what got auto-fixed and what's in the
digest's "Needs you" section, briefly — a clean run deserves a one-line reply, not a
full report.

Thin wrapper around `toolkit/uikit/` — the harness that turns "looks right to me" into
a check that can fail. Don't re-implement screenshot capture or asset-checking by hand
when this exists; it encodes lessons that are easy to get wrong the first time (see
below), and re-deriving them from scratch is how those exact mistakes happen again.

## Locating the toolkit

Look for `toolkit/uikit/` in the current repo first. If this session doesn't have it,
check whether it's mirrored into a `jcwork`-style repo this session has access to
(`toolkit/skills/` ships alongside it via `toolkit/uikit/../skills` — same parent
`toolkit/` directory) and use `toolkit/install.sh` to place a copy, or run `npm
install` directly inside a copy of `toolkit/uikit/` (needs `playwright-core`,
`pixelmatch`, `pngjs` — see its `package.json`). It launches Chromium via an explicit
`executablePath`, not Playwright's own browser management, so it works with whatever
Chromium binary is already on the machine (this environment has one preinstalled at
`/opt/pw-browsers/`).

## When to use this

- The user asks to check, review, verify, or "look at" a web page or mockup.
- Any time you are about to report a UI/design task as finished — verification is not
  optional polish, it's part of what "done" means. `designing-websites` (if that skill
  is loaded) requires this as its Phase 4.
- Before a mockup ships / gets zipped / gets handed off.

## The commands

```bash
# One-shot pass/fail gate — the one to reach for by default.
node toolkit/uikit/gate.mjs <target-dir>                    # check
node toolkit/uikit/gate.mjs <target-dir> --update-baseline  # (re-)establish baseline

# The individual tools gate.mjs composes, for when you need just one:
node toolkit/uikit/shoot.mjs <target-dir> --out <dir>         # screenshots only
node toolkit/uikit/audit.mjs <target-dir> --out <dir>         # findings, no baseline diff
node toolkit/uikit/audit.mjs <target-dir> --tier1-only        # static checks only, <1s
node toolkit/uikit/diff.mjs <baselineDir> <currentDir>        # compare two screenshot sets directly
```

`<target-dir>` is the site's root — every tool takes it as the first argument, so
these run against any target, including a read-only checkout you can't push to.
`gate.mjs` fails fast: static checks (ms) run before a browser ever launches, and a
static failure skips the rendered pass entirely — so a fast failure usually means the
finding is in the static tier (missing files, broken refs, version mismatch), not
rendered.

## Read the findings; two severities mean different things

`audit.mjs` (and therefore `gate.mjs`) reports `error` and `warning`. `gate.mjs`
blocks on both — treat every finding in a gate failure as something to fix, not
triage. If you're running `audit.mjs` directly rather than through the gate: `error`
is unambiguous (broken reference, mismatched version stamp, a request off `file://`);
`warning` is currently contrast findings only, which need a judgment call — some
low-contrast text is a deliberate muted/disabled state, not every warning is a bug.

## Why `reducedMotion` and request-blocking matter, concretely

Rendering `EW_Studio_Collections_V3.0`'s `html/index.html` without forcing
`reducedMotion` produces a screenshot where the entire pricing section — three tier
cards, all prices, both buttons — is black-on-black and invisible. The section reveals
via `opacity: 0` + `IntersectionObserver` on scroll
(`html/assets/campaign.css:696`, `campaign.js:206`); a static capture never scrolls, so
nothing below the fold ever becomes visible without it. `lib.mjs` forces
`reducedMotion: 'reduce'` for exactly this reason, and separately blocks every
non-`file://` request the page attempts (logging each one) — which is how the same
target's "no internet needed" claim in `READ-ME-FIRST.txt` was caught being false (it
fetches three Google Fonts). Both are on by default; don't build a parallel screenshot
path that skips them.
