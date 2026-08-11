---
name: brand-identity
description: Provides the single source of truth for brand guidelines, design tokens, technology choices, and voice/tone. Use this skill whenever generating UI components, styling applications, writing copy, or creating user-facing assets to ensure brand consistency.
---

# Brand Identity & Guidelines

**Brand:** EastWest Studio Collections (`julious360/EW_Studio_Collections_V3.0`)

This skill defines the core constraints for visual design and technical implementation
for the brand. You must adhere to these guidelines strictly to maintain consistency.

The three resource files below are seeded from real, verified content in that
project — the design tokens were machine-extracted from its shipped `campaign.css`
(via `toolkit/uikit/tokens.mjs` in `jcwork`, not hand-copied), and the tech-stack and
voice-tone notes cite specific files and real shipped copy rather than generic
best-practice advice. **To repoint this skill at a different brand**, replace the
content of the three resource files with that brand's real tokens/stack/voice — the
instructions above stay the same regardless of which brand's data lives underneath.

## Reference Documentation

Depending on the task you are performing, consult the specific resource files below. Do not guess brand elements; always read the corresponding file.

### For Visual Design & UI Styling
If you need exact colors, fonts, border radii, or spacing values, read:
👉 **[`resources/design-tokens.json`](resources/design-tokens.json)**

### For Coding & Component Implementation
If you are generating code, choosing libraries, or structuring UI components, read the technical constraints here:
👉 **[`resources/tech-stack.md`](resources/tech-stack.md)**

### For Copywriting & Content Generation
If you are writing marketing copy, error messages, documentation, or user-facing text, read the persona guidelines here:
👉 **[`resources/voice-tone.md`](resources/voice-tone.md)**
