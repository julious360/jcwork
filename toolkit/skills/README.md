# toolkit/skills — versioned skill library

The personal Claude skill library, version-controlled here instead of living only at
`~/.claude/skills` on one machine. That was the actual problem being fixed: not that
the skills were bad (some, like `music-plugin-ux`, were genuinely good — real numeric
specs, explicit anti-patterns) but that the library had no git history, no portability,
and two of the four skills here were broken in ways nobody would notice until an agent
tried to use them and hit a missing file or an un-runnable step.

## Install

```bash
toolkit/skills/install.sh                       # every skill here -> ~/.claude/skills/
toolkit/skills/install.sh brand-identity         # just one
```

## What's here

- **`brand-identity`** — was pointing at three resource files that didn't exist
  (`resources/design-tokens.json`, `tech-stack.md`, `voice-tone.md`), had duplicated
  YAML frontmatter, and still said `[INSERT BRAND NAME HERE]`. Fixed and seeded with
  real, machine-extracted data: the design tokens come from
  `EW_Studio_Collections_V3.0`'s actual shipped `campaign.css` (via
  `toolkit/uikit/tokens.mjs extract`, not hand-copied), and the tech-stack/voice-tone
  notes cite specific files and real shipped copy. Swap the three resource files'
  content to repoint this at a different brand.
- **`designing-websites`** — was not executable by an agent: it instructed opening
  "Google Stitch," prompting "Gemini," and launching an "Antigravity 2.0 Standalone
  Desktop App," none of which an agent can do. Rewritten so every step is something
  this agent can run: plain HTML wireframe → `design-tokens.json` → CSS driven by the
  tokens → mandatory verification via `toolkit/uikit/gate.mjs`.
- **`creative-director-sterling-elite-graphic-typography-designer`** — was a pure
  persona ("You are Creative Director Sterling, 30 years of experience...") with no
  concrete constraints underneath. Converted to explicit constraints (name real
  typefaces and hex values, not adjectives; luxury design specifically flagged against
  clutter) plus a worked example, keeping the one genuinely useful part of the
  original: always producing 2-3 distinct directions instead of one answer.
- **`ui-verify`** — new. Thin wrapper pointing at `toolkit/uikit/` (`shoot.mjs` /
  `diff.mjs` / `audit.mjs` / `gate.mjs`) so "check this page" or "is this done"
  reliably triggers the verification harness instead of an eyeball pass.

## Why these four and not the others in `~/.claude/skills`

`music-plugin-ux` was already good and needed no repair. `error-handling-patterns` and
the five `INSTRUCTIONS`-repo notes are generic knowledge with no project-specific
constraint — lower leverage to fix than the four above, which were either broken
outright or actively misleading an agent that tried to follow them.
