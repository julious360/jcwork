---
name: ad-concept-brief
description: Turn a customer pain point into a brand-safe Meta ad concept brief — hook, primary text, headline, visual direction, and the validator checks it must pass. Use when asked for ad concepts, ad copy, creative briefs, or new angles to test.
---

# Ad Concept Brief

Produces a brief that `agent/creative/pipeline.py` can execute and
`agent/creative/brand_validator.py` will accept on the first pass.

## Inputs

1. A pain point — verbatim customer language, ideally from `adagent research`.
2. `agent/config/campaign.yaml` — product, value proposition, ICP. Read it; never
   invent product claims.
3. `references/brand-tokens.json` — palette, fonts, ad spec, forbidden claims.
   This mirrors `agent/config/brand_guide.yaml`; if they disagree, the YAML wins and
   the tokens file is stale — say so.

## Procedure

1. Read `campaign.yaml` and `references/brand-tokens.json`.
2. Check novelty before writing: `adagent actions --limit 50` (and, if available,
   the last shipped concepts). A concept whose angle restates a recent winner will be
   rejected by `agent/entropy/novelty.py` at `novelty_threshold: 0.88`. Change the
   angle, not the wording.
3. Fill `references/concept-brief.template.md`. Every field is required.
4. Self-validate against the checklist below and state the result. A brief that fails
   its own checklist is not delivered — fix it first.

## Copy constraints (hard)

- Primary text ≤ 125 characters before the "See more" fold; headline ≤ 40; description ≤ 30.
- Tone: confident, plain-spoken, concrete. No hype, no exclamation marks.
- Forbidden claims (substring match, case-insensitive):
  `guaranteed`, `#1`, `best in the world`, `risk-free`, `instantly`.
- One idea per concept. If it needs "and also", it's two concepts.

## Visual constraints (deterministic — measured, not judged)

- Aspect ratio ∈ {1:1, 4:5, 9:16}, tolerance 0.02. Min width 1080px. ≤ 30 MB.
- Text coverage ≤ 20% of pixels.
- ≥ 25% of pixels on-palette, ΔE (CIE76) ≤ 12 from the nearest palette colour.
- Logo in a corner, clear space ≥ its own cap-height, never recoloured or rotated.

## Self-check before delivering

- [ ] Angle is distinct from the last 50 ledger actions
- [ ] Character counts inside limits
- [ ] Zero forbidden claims
- [ ] Named aspect ratio is in the allowed set
- [ ] Visual direction names specific palette tokens by name, not vibes
- [ ] Every product claim traces to `campaign.yaml`

## Headless

```bash
claude -p "/ad-concept-brief 'clients keep changing scope mid-project'" \
  --output-format text > memory/outbox/briefs/$(date +%F)-scope-creep.md
```
