---
name: designing-websites
description: Automates the transition of website layouts from text concepts to structured wireframes, applied design tokens, high-definition comps, and deployment-ready frontend code. Use when the user asks to design, style, or build a website or landing page.
---

# End-to-End Web Design & Development

## When to use this skill
- When the user asks to design, style, or build a website or landing page.
- When transitioning a website concept from a text description to structured wireframes, applied design tokens, high-definition comps, and frontend code.

Every step below is something this agent can actually run: no external GUI, no
desktop app, no service the agent can't reach. A previous version of this skill
instructed opening "Google Stitch," feeding it to "Gemini," and launching an
"Antigravity 2.0 Standalone Desktop App" — none of which an agent can do, which made
the skill un-executable from step 1. This version replaces each of those with a real
tool: plain HTML for structure, a `design-tokens.json` for tokens, hand-authored
CSS/JS for the hi-fi build, and the `uikit` toolkit (`toolkit/uikit/` — see the
`ui-verify` skill) for verification.

## Workflow
Create a task checklist for these phases and complete them in order:
1. [ ] **Wireframe** — plain HTML skeleton, structure and hierarchy only, no styling.
2. [ ] **Tokens** — a `design-tokens.json` (colors, type, radius, spacing) as the
   single source of truth for the hi-fi build.
3. [ ] **Hi-fi build** — real HTML/CSS/JS driven by the tokens.
4. [ ] **Verify** — render it and prove it, don't eyeball it. This is not optional:
   a page has not been "designed" until it has been rendered and checked, not just
   written.

## Instructions

### 1. Wireframe
Write the page as plain HTML: real tags, real content hierarchy (heading levels,
landmark elements — `<header>`, `<nav>`, `<section>`, `<footer>` — semantic
structure), placeholder or draft copy, no `<style>` and no CSS framework yet. The
goal is a structure a reviewer could judge on hierarchy and flow alone, the same
reason a low-fidelity wireframe is useful in any design process — just written
directly as markup instead of drawn as boxes in an external tool.

### 2. Tokens
Produce a `design-tokens.json` — the same shape `toolkit/uikit/tokens.mjs` reads and
writes: `{ "tokens": { "<name>": "<value>" }, "variants": { "<class>": {...} } }`.
Two ways to get one, in order of preference:
- **A real palette already exists somewhere in the project or a sibling project.**
  Extract it rather than inventing a new one: `node tokens.mjs extract
  <existing.css> --out design-tokens.json`. This is how `brand-identity`'s tokens
  were seeded — from EastWest Studio Collections' actual shipped `campaign.css`, not
  hand-typed.
- **No existing palette.** Write `design-tokens.json` by hand: pick specific hex
  values, a type scale, a radius, spacing — not vague descriptions ("a blue accent")
  but literal values a stylesheet can use directly.

Once you have it, generate the CSS from it — don't hand-write a `:root` block that
can drift from the JSON: `node tokens.mjs generate design-tokens.json --out
tokens.css`.

### 3. Hi-fi build
Apply `tokens.css` to the wireframe's structure. Build real, responsive CSS —
`var(--token-name)` throughout, not literal values re-typed from the token file (that
reintroduces exactly the single-source-of-truth problem the tokens file exists to
prevent). Add interaction JS as needed. If the project has (or should have) a
`data/*.json` content source loaded by a generated `*-data.js` wrapper (the pattern
documented in `brand-identity`'s `resources/tech-stack.md`, load that skill for
detail if the target runs from `file://` with no server), follow it rather than
`fetch()`-ing local JSON.

Optionally generate `gallery.html` at this point (`node gallery.mjs
design-tokens.json`) — a page rendering every color/variant/button/card state from
the tokens in one place. It's a fast way to eyeball a token change's blast radius
before it's spread across every page.

### 4. Verify — required, not optional
Run the gate, not a visual skim:

```bash
node toolkit/uikit/gate.mjs <path-to-the-site> --update-baseline   # first run: establishes baseline
node toolkit/uikit/gate.mjs <path-to-the-site>                     # every run after: must PASS
```

This checks, mechanically, what an eyeball pass reliably misses: broken asset
references, orphaned images, a stale generated data file, a version-stamp mismatch,
WCAG contrast, horizontal overflow, and any request the page makes off `file://`
(the "works offline" claim, if the project makes one). A concrete example from this
same toolkit's own verification: the EastWest Studio Collections mockup renders its
pricing section via `opacity: 0` + scroll-reveal — a screenshot taken without
`reducedMotion` forced shows that section blank, which looks like a catastrophic bug
and isn't one. `gate.mjs` (via `shoot.mjs`) already forces `reducedMotion` for exactly
this reason; don't re-implement screenshot capture by hand and lose that.

Don't report the design as done until `gate.mjs` passes. If it fails, fix the finding
— don't lower the bar by skipping the check.
