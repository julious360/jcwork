#!/usr/bin/env node
// Generates a self-contained component gallery from a design-tokens.json: every
// color, the type scale, and a representative set of components (buttons, card,
// tier/variant swatches) rendered in their states on one static page.
//
// This is the real component library the plan calls for — running code that
// renders from the tokens, not a markdown spec describing what a button should
// look like. It's also the highest-value target for shoot.mjs/diff.mjs: a token
// change shows up as a visual diff across every component at once, on one page,
// instead of requiring someone to remember which components use which token.
//
// Tokens are embedded inline (a <script>const TOKENS = {...}</script> block, not a
// fetch() of a sibling JSON file) for the same reason EW's own DESIGNER-GUIDE.md
// documents for its collections-data.js wrapper: a file:// page can't reliably
// fetch() a local file due to the browser's CORS policy for the file: origin, so
// the working pattern already established in this codebase's own tooling is to
// inline the data as a script instead. gallery.html reuses that pattern rather
// than reintroducing the problem it was designed around.
//
// Usage:
//   node gallery.mjs <tokens.json> [--out gallery.html]

import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { generateCss } from "./tokens.mjs";

function parseArgs(argv) {
  const [tokensPath, ...rest] = argv;
  if (!tokensPath) {
    console.error("usage: node gallery.mjs <tokens.json> [--out gallery.html]");
    process.exit(2);
  }
  let out = path.join(path.dirname(path.resolve(tokensPath)), "gallery.html");
  for (let i = 0; i < rest.length; i++) {
    if (rest[i] === "--out") out = rest[++i];
  }
  return { tokensPath: path.resolve(tokensPath), out: path.resolve(out) };
}

const COLOR_RE = /^#[0-9a-f]{3,8}$|^rgba?\(|^hsla?\(/i;

function tokenValue(t) {
  return typeof t === "string" ? t : t.value;
}

function colorSwatches(tokens) {
  return Object.entries(tokens)
    .filter(([, t]) => COLOR_RE.test(tokenValue(t).trim()))
    .map(
      ([name, t]) => `
      <div class="swatch">
        <div class="swatch-fill" style="background: var(--${name})"></div>
        <code>--${name}</code>
        <span class="swatch-value">${tokenValue(t)}</span>
      </div>`
    )
    .join("");
}

function variantSwatches(variants) {
  return Object.entries(variants)
    .map(([className, decls]) => {
      const accent = decls.accent ?? decls.acc ?? "var(--accent, #888)";
      return `
      <div class="variant ${className}" style="${Object.entries(decls)
        .map(([k, v]) => `--${k}:${v}`)
        .join(";")}">
        <div class="variant-chip" style="background:${accent}"></div>
        <code>.${className}</code>
      </div>`;
    })
    .join("");
}

function renderGallery(tokensDoc) {
  const generatedCss = generateCss(tokensDoc);
  const swatches = colorSwatches(tokensDoc.tokens ?? {});
  const variants = variantSwatches(tokensDoc.variants ?? {});

  return `<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Component Gallery — generated from ${path.basename(tokensDoc.source ?? "design-tokens.json")}</title>
<style>
${generatedCss}
/* ---- gallery chrome: reads the tokens above, with generic fallbacks so this
   renders something reasonable even against a tokens.json missing a few names ---- */
* { box-sizing: border-box; }
body {
  margin: 0; padding: 40px;
  background: var(--bg, #0b0b0f);
  color: var(--ink, #eee);
  font-family: var(--font, system-ui, sans-serif);
}
h1, h2 { font-family: var(--display, var(--font, sans-serif)); font-weight: 700; }
h1 { font-size: 28px; margin: 0 0 4px; }
.meta { color: var(--ink-mute, #888); font-size: 13px; margin-bottom: 40px; }
section { margin-bottom: 48px; }
h2 { font-size: 16px; text-transform: uppercase; letter-spacing: .08em; color: var(--ink-soft, #ccc);
     border-bottom: 1px solid var(--line, #333); padding-bottom: 8px; margin-bottom: 20px; }

.row { display: flex; flex-wrap: wrap; gap: 16px; align-items: flex-start; }

.swatch { width: 140px; }
.swatch-fill { height: 60px; border-radius: var(--radius, 6px); border: 1px solid var(--line, #333); }
.swatch code { display: block; font-size: 11px; margin-top: 6px; color: var(--ink-soft, #ccc); }
.swatch-value { display: block; font-size: 11px; color: var(--ink-mute, #888); }

.variant { padding: 12px; border-radius: var(--radius, 6px); border: 1px solid var(--line, #333); display: flex; align-items: center; gap: 8px; }
.variant-chip { width: 20px; height: 20px; border-radius: 50%; }
.variant code { font-size: 12px; }

.btn { display: inline-block; padding: 10px 20px; border-radius: var(--radius, 6px); font-weight: 700;
       font-family: var(--display, var(--font, sans-serif)); text-decoration: none; border: 1px solid transparent;
       font-size: 14px; cursor: pointer; }
.btn-primary { background: var(--accent, #4a7dff); color: var(--on-accent, #fff); }
.btn-secondary { background: transparent; color: var(--accent, #4a7dff); border-color: var(--accent, #4a7dff); }
.btn[disabled] { opacity: .4; cursor: not-allowed; }
.btn-primary:hover, .btn-primary.is-hover { background: var(--accent-hi, var(--accent, #4a7dff)); }

.card { width: 260px; padding: 20px; border-radius: var(--radius, 6px); background: var(--panel, #161616);
        border: 1px solid var(--line, #333); }
.card h3 { margin: 0 0 8px; font-size: 16px; }
.card p { margin: 0; color: var(--ink-soft, #ccc); font-size: 13px; line-height: 1.5; }
.card.is-hover { border-color: var(--accent, #4a7dff); }

.type-scale div { margin-bottom: 12px; }
.type-h1 { font-size: 40px; }
.type-h2 { font-size: 28px; }
.type-body { font-size: 15px; font-family: var(--font, sans-serif); font-weight: 400; }
.type-mute { font-size: 13px; color: var(--ink-mute, #888); }
</style>
</head>
<body>
<h1>Component Gallery</h1>
<div class="meta">Generated from <code>${tokensDoc.source ?? "design-tokens.json"}</code> — ${tokensDoc.extractedAt ?? ""}</div>

<section>
  <h2>Color tokens</h2>
  <div class="row">${swatches || "<p>No color-shaped tokens found.</p>"}</div>
</section>

${
  variants
    ? `<section>
  <h2>Variants</h2>
  <div class="row">${variants}</div>
</section>`
    : ""
}

<section>
  <h2>Typography</h2>
  <div class="type-scale">
    <div class="type-h1">Heading — var(--display)</div>
    <div class="type-h2">Subheading</div>
    <div class="type-body">Body text sample, set in var(--font). The quick brown fox jumps over the lazy dog.</div>
    <div class="type-mute">Muted / secondary text, var(--ink-mute).</div>
  </div>
</section>

<section>
  <h2>Buttons</h2>
  <div class="row">
    <a class="btn btn-primary">Primary</a>
    <a class="btn btn-primary is-hover">Primary — hover</a>
    <a class="btn btn-primary" disabled>Primary — disabled</a>
    <a class="btn btn-secondary">Secondary</a>
    <a class="btn btn-secondary" disabled>Secondary — disabled</a>
  </div>
</section>

<section>
  <h2>Card</h2>
  <div class="row">
    <div class="card">
      <h3>Card title</h3>
      <p>Default state, rendered from --panel, --line, --ink-soft.</p>
    </div>
    <div class="card is-hover">
      <h3>Card title</h3>
      <p>Hover state, border switches to --accent.</p>
    </div>
  </div>
</section>

</body>
</html>
`;
}

const isMain = import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
  const { tokensPath, out } = parseArgs(process.argv.slice(2));
  const tokensDoc = JSON.parse(await readFile(tokensPath, "utf8"));
  const html = renderGallery(tokensDoc);
  await writeFile(out, html);
  console.log(`uikit gallery: rendered ${Object.keys(tokensDoc.tokens ?? {}).length} tokens, ${Object.keys(tokensDoc.variants ?? {}).length} variant(s) -> ${out}`);
}

export { renderGallery };
