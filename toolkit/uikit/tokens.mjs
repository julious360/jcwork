#!/usr/bin/env node
// Design tokens as a two-way bridge between a CSS `:root` block and a portable JSON
// file. `extract` turns an existing stylesheet's tokens into design-tokens.json (how
// the brand-identity skill gets seeded from a real, shipped palette instead of a
// placeholder). `generate` does the reverse, so the JSON can stay the single source
// of truth and the CSS becomes a build artifact instead of the place tokens live.
//
// Usage:
//   node tokens.mjs extract <css-file> [--out tokens.json] [--selector :root]
//   node tokens.mjs generate <tokens.json> [--out file.css] [--selector :root]

import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";

function parseArgs(argv) {
  const [cmd, input, ...rest] = argv;
  if (!cmd || !input || !["extract", "generate"].includes(cmd)) {
    console.error("usage: node tokens.mjs extract <css-file> [--out tokens.json] [--selector :root]");
    console.error("       node tokens.mjs generate <tokens.json> [--out file.css] [--selector :root]");
    process.exit(2);
  }
  let out = null;
  let selector = ":root";
  for (let i = 0; i < rest.length; i++) {
    if (rest[i] === "--out") out = rest[++i];
    else if (rest[i] === "--selector") selector = rest[++i];
  }
  return { cmd, input: path.resolve(input), out, selector };
}

/** Pull `--name: value;` custom-property declarations out of one CSS block
 *  (default `:root`). Comments on the same line as a declaration are kept as the
 *  token's `note` — campaign.css uses these for things like "gold (brand)" that
 *  are worth preserving, not discarding. */
export function extractTokens(css, selector = ":root") {
  const blockRe = new RegExp(`${selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\{([^}]*)\\}`, "s");
  const match = css.match(blockRe);
  if (!match) return {};
  const body = match[1];
  const tokens = {};
  const declRe = /--([a-zA-Z0-9-]+)\s*:\s*([^;]+);(?:\s*\/\*\s*(.*?)\s*\*\/)?/g;
  for (const m of body.matchAll(declRe)) {
    const [, name, value, note] = m;
    tokens[name] = note ? { value: value.trim(), note: note.trim() } : value.trim();
  }
  return tokens;
}

/** All selectors of the form `.name { --a:v; ... }` — theme/tier variants that
 *  override a subset of tokens for a scoped context (EW's .tier-producer /
 *  .tier-hollywood / .tier-complete pattern). Kept separate from the base tokens
 *  rather than flattened, since a consumer needs to know these apply conditionally. */
export function extractVariants(css) {
  const variants = {};
  const ruleRe = /\.([a-zA-Z0-9-]+)\s*\{([^}]*--[^}]*)\}/g;
  for (const m of css.matchAll(ruleRe)) {
    const [, className, body] = m;
    const declRe = /--([a-zA-Z0-9-]+)\s*:\s*([^;]+);/g;
    const decls = {};
    for (const d of body.matchAll(declRe)) decls[d[1]] = d[2].trim();
    if (Object.keys(decls).length > 0) variants[className] = decls;
  }
  return variants;
}

function tokenValue(t) {
  return typeof t === "string" ? t : t.value;
}

export function generateCss(tokensDoc, selector = ":root") {
  const lines = [`${selector} {`];
  for (const [name, t] of Object.entries(tokensDoc.tokens ?? {})) {
    const note = typeof t === "object" && t.note ? `  /* ${t.note} */` : "";
    lines.push(`  --${name}: ${tokenValue(t)};${note}`);
  }
  lines.push("}");

  for (const [className, decls] of Object.entries(tokensDoc.variants ?? {})) {
    lines.push("", `.${className} {`);
    for (const [name, value] of Object.entries(decls)) lines.push(`  --${name}: ${value};`);
    lines.push("}");
  }

  return lines.join("\n") + "\n";
}

const isMain = import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
  const { cmd, input, out, selector } = parseArgs(process.argv.slice(2));

  if (cmd === "extract") {
    const css = await readFile(input, "utf8");
    const doc = {
      source: input,
      extractedAt: new Date().toISOString(),
      selector,
      tokens: extractTokens(css, selector),
      variants: extractVariants(css),
    };
    const json = JSON.stringify(doc, null, 2) + "\n";
    if (out) {
      await writeFile(out, json);
      console.log(`uikit tokens: extracted ${Object.keys(doc.tokens).length} tokens, ${Object.keys(doc.variants).length} variant(s) -> ${out}`);
    } else {
      process.stdout.write(json);
    }
  } else {
    const doc = JSON.parse(await readFile(input, "utf8"));
    const css = generateCss(doc, doc.selector ?? selector);
    if (out) {
      await writeFile(out, css);
      console.log(`uikit tokens: generated ${selector} block -> ${out}`);
    } else {
      process.stdout.write(css);
    }
  }
}
