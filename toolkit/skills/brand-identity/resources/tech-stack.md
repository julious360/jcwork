# Tech Stack & Technical Constraints

Grounded in the actual shipped implementation (`EW_Studio_Collections_V3.0` /
`html/`), not aspirational — every rule below was verified against real files in this
session, not assumed.

## Stack

- **Vanilla HTML/CSS/JS. No framework, no build step.** `html/*.html` are hand-authored
  pages; `html/assets/campaign.css` and `campaign.js` are plain files loaded via
  `<link>`/`<script>`, no bundler in the pipeline.
- **Must run from `file://` with no server.** Pages are opened by double-clicking
  `index.html`. This constrains what's allowed:
  - **No `fetch()` of local JSON.** Chromium's CORS policy blocks a `file://` page from
    fetching a sibling local file. The data-loading pattern here is a generated JS
    wrapper instead: `data/collections.json` is the source of truth, but the page
    actually loads `html/assets/collections-data.js`, which is
    `window.COLLECTIONS = <the same JSON>;` — a plain `<script>` tag, no fetch. If you
    add a new local JSON data source, follow this same wrapper pattern rather than
    reaching for `fetch()`.
  - Relative asset paths (`src=`, `href=`, CSS `url()`) resolve exactly as the browser
    resolves any relative URL — relative to the referencing file's own directory. A
    page in `html/` reaching an image in `links/` at the project root writes
    `../links/…`; a stylesheet at `html/assets/` writes `../../links/…`.
- **Fonts:** the display face (Tachyon) is self-hosted as a `.woff2` under
  `html/assets/fonts/` and works offline. Body faces (Inter, DM Sans) are currently
  loaded from `fonts.googleapis.com` — a real, unresolved gap between this and the "no
  internet needed" claim in this project's own `READ-ME-FIRST.txt`. Prefer self-hosting
  any new font the same way Tachyon is already handled, rather than adding another
  Google Fonts `<link>`.
- **No cart, no checkout, no login.** Buttons for these exist as visual affordances
  only — this is a design mockup, not a store. Don't wire real commerce logic into
  markup meant to stay a mockup unless the task explicitly asks for that.

## Verification

This project pairs with `toolkit/uikit/` (in the `jcwork` repo): `shoot.mjs` for
deterministic screenshots, `diff.mjs` for visual regression, `audit.mjs` for asset
integrity / contrast / offline-guarantee checks, and `gate.mjs` composing all three into
a pre-handoff gate. Run `node gate.mjs <path-to-this-project>` before treating any
change as finished — see the `ui-verify` skill.
