#!/usr/bin/env node
// Static + rendered checks a human reviewer tends to miss by eye: files a doc
// references but the repo doesn't have, image/CSS/data refs that resolve to
// nothing, orphaned assets, a VERSION file that disagrees with the on-page banner,
// a generated *-data.js that has drifted from its source JSON, stray backup
// directories, WCAG AA contrast, horizontal overflow, and any request a page makes
// off file://.
//
// Usage:
//   node audit.mjs <target-dir> [--out <dir>] [--tier1-only]
//
// Findings carry a severity: "error" fails audit.mjs's own exit code; "warning"
// (currently: contrast only) is reported but doesn't. Contrast is judgment-prone —
// some low-contrast text is a deliberate muted/disabled state — so it's surfaced,
// not auto-failed, here. gate.mjs (the pre-handoff gate) is stricter: it treats
// every finding, warnings included, as blocking. Two different consumers, two
// different bars for the same evidence.

import { readFile, writeFile, mkdir, readdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { openPage, forceRevealAll, findPages, checkContrast, checkHorizontalOverflow, BREAKPOINTS } from "./lib.mjs";

const ASSET_EXT = /\.(jpe?g|png|gif|svg|webp|avif|mp4|webm|woff2?|ttf|otf|ico)$/i;
// Used for the general "which files do I scan for references" walk. Must NOT
// exclude "html" — that's where the referencing pages/CSS/JS live. A first version
// of this excluded it (reasoning, wrongly, that html/ holds "pages, not delivered
// media"), which meant html/*.html, html/assets/campaign.css, and campaign.js were
// never read at all: every asset in links/ came back "orphaned" purely because
// nothing that references them was ever scanned. Caught by spot-checking one
// specific flagged file (links/box-complete.jpg, referenced directly from
// campaign.css:627) that plainly should not have been orphaned.
const DEFAULT_EXCLUDE_DIRS = new Set(["node_modules", ".git", "_backup", "z_backup", "references", "images"]);
// "images" stays excluded: by this project's own convention (README) it holds
// local-only raw masters, deliberately not part of the shipped deliverable — and it
// contains no HTML/CSS/JSON to scan for references in the first place.

function parseArgs(argv) {
  const [targetDir, ...rest] = argv;
  if (!targetDir) {
    console.error("usage: node audit.mjs <target-dir> [--out <dir>] [--tier1-only]");
    process.exit(2);
  }
  let out = path.join(process.cwd(), "uikit-output", "audit");
  let tier1Only = false;
  for (let i = 0; i < rest.length; i++) {
    if (rest[i] === "--out") out = rest[++i];
    else if (rest[i] === "--tier1-only") tier1Only = true;
  }
  return { targetDir: path.resolve(targetDir), out: path.resolve(out), tier1Only };
}

async function loadConfig(targetDir) {
  const p = path.join(targetDir, "toolkit-uikit.config.json");
  if (!existsSync(p)) return {};
  return JSON.parse(await readFile(p, "utf8"));
}

async function walk(dir, exclude, out = []) {
  let entries;
  try {
    entries = await readdir(dir, { withFileTypes: true });
  } catch {
    return out;
  }
  for (const e of entries) {
    if (exclude.has(e.name)) continue;
    const full = path.join(dir, e.name);
    if (e.isDirectory()) await walk(full, exclude, out);
    else out.push(full);
  }
  return out;
}

function finding(severity, check, message, extra = {}) {
  return { severity, check, message, ...extra };
}

// ── Tier 1: static, no browser ──────────────────────────────────────────────────

/** Backtick-quoted, path-shaped strings in *.md/*.txt files that don't resolve.
 *  This is how a doc telling the assistant "point it at CLAUDE.md first" gets
 *  checked without hardcoding any project's specific file list.
 *
 *  CHANGELOG-shaped files are excluded: verified against this project's own
 *  CHANGELOG.md, which narrates history ("replaced sc-box-hero.jpg with...",
 *  "archived to z_backup/...") and by nature names files that no longer exist on
 *  purpose — they were renamed, replaced, or archived. Scanning it the same way as
 *  README/DESIGNER-GUIDE (which describe current state and tell the reader to open
 *  a specific file right now) produced dozens of false positives from ordinary
 *  changelog prose, drowning out the real findings in the docs that matter. */
async function checkDocReferencedFiles(targetDir, allFiles) {
  const findings = [];
  const docFiles = allFiles.filter((f) => /\.(md|txt)$/i.test(f) && !/changelog/i.test(path.basename(f)));
  // Bare filenames in prose ("open index.html") are common and don't specify a full
  // path — verified against this project's own README, which names `index.html`,
  // `collections.json`, and `assets/collections-data.js` without their `html/` or
  // `data/` prefixes because the surrounding prose already establishes that context.
  // Resolving root-relative-only produced false positives for all three, even
  // though each genuinely exists. A file actually present anywhere in the tree
  // (basename match, excluding _backup/node_modules/.git) counts as resolved.
  const basenameIndex = new Map();
  for (const f of allFiles) {
    const key = path.basename(f);
    if (!basenameIndex.has(key)) basenameIndex.set(key, []);
    basenameIndex.get(key).push(f);
  }

  const pathLike = /`([a-zA-Z0-9_.-][a-zA-Z0-9_./-]*\.[a-zA-Z0-9]{1,5}|[a-zA-Z0-9_.-][a-zA-Z0-9_./-]*\/)`/g;
  const seen = new Set();
  for (const doc of docFiles) {
    const text = await readFile(doc, "utf8");
    for (const m of text.matchAll(pathLike)) {
      const ref = m[1];
      if (ref.includes("://") || ref.startsWith("#")) continue;
      const key = `${doc}::${ref}`;
      if (seen.has(key)) continue;
      seen.add(key);

      const isDir = ref.endsWith("/");
      const bare = ref.replace(/\/$/, "");
      const resolvedDirect = path.join(targetDir, bare);
      const resolvedAnywhere = basenameIndex.get(path.basename(bare));
      if (existsSync(resolvedDirect) || (resolvedAnywhere && resolvedAnywhere.length > 0)) continue;

      // Directory-shaped refs are lower-confidence: this project documents some of
      // them (images/, references/) as deliberately excluded local-only source, a
      // pattern a static scanner can't distinguish from a genuinely dropped
      // directory like md/. File-shaped refs with an extension (CLAUDE.md,
      // export.sh) are a much stronger signal and stay at error severity.
      findings.push(
        finding(
          isDir ? "warning" : "error",
          "doc-referenced-file-missing",
          `${path.relative(targetDir, doc)} references \`${ref}\`, which does not exist`,
          { doc: path.relative(targetDir, doc), ref }
        )
      );
    }
  }
  return findings;
}

function extractRefsFromHtml(html) {
  const refs = [];
  for (const m of html.matchAll(/\b(?:src|href)\s*=\s*["']([^"'#][^"']*)["']/gi)) refs.push(m[1]);
  for (const m of html.matchAll(/url\(\s*["']?([^"')]+)["']?\s*\)/gi)) refs.push(m[1]);
  return refs;
}

function extractRefsFromCss(css) {
  return [...css.matchAll(/url\(\s*["']?([^"')]+)["']?\s*\)/gi)].map((m) => m[1]);
}

/** Quoted, asset-shaped string literals in JS source — a page can build markup
 *  dynamically ("$" + `<img src="${x}">`) or hold a plain array/object literal of
 *  image paths that never touches JSON.parse, and neither would be seen by the
 *  HTML/CSS/JSON extractors above. Verified this gap wasn't hiding anything on the
 *  EW target (its 9 orphans checked against campaign.js turned up no matches), but
 *  it's a real blind spot for the general case, so it's covered rather than assumed
 *  away for whatever site runs through this next. */
function extractRefsFromJs(js) {
  return [...js.matchAll(/["'`]([^"'`]+\.(?:jpe?g|png|gif|svg|webp|avif|mp4|webm|woff2?|ttf|otf|ico))["'`]/gi)].map((m) => m[1]);
}

function extractAssetRefsFromJson(value, refs = []) {
  if (typeof value === "string") {
    if (!/^https?:\/\//i.test(value) && ASSET_EXT.test(value)) refs.push(value);
  } else if (Array.isArray(value)) {
    for (const v of value) extractAssetRefsFromJson(v, refs);
  } else if (value && typeof value === "object") {
    for (const v of Object.values(value)) extractAssetRefsFromJson(v, refs);
  }
  return refs;
}

function isLocal(ref) {
  return !/^([a-z]+:)?\/\//i.test(ref) && !ref.startsWith("data:") && !ref.startsWith("mailto:") && !ref.startsWith("tel:");
}

/** Every src=/href=/url()/JSON asset-shaped string, resolved relative to its
 *  referencing file, plus which shipped-asset-directory files nothing points at. */
async function checkAssetIntegrity(targetDir, config, allFiles) {
  const findings = [];
  const referenced = new Set();

  for (const file of allFiles) {
    let refs = [];
    // HTML/CSS relative URLs resolve against the referencing file's own directory —
    // that's a real, browser-enforced rule. A JSON data file has no such rule: it's
    // just strings. Verified against this project's own collections.json: its "art"
    // paths ("links/pianos.jpg") are root-relative, matching how the pages that
    // consume the generated data/*.js wrapper resolve them — resolving against
    // collections.json's own directory instead produced "data/links/pianos.jpg" and
    // flagged an image that is actually present. Fixed by resolving JSON refs
    // against the target root rather than the JSON file's directory.
    let resolveBase = path.dirname(file);
    if (/\.html?$/i.test(file)) refs = extractRefsFromHtml(await readFile(file, "utf8"));
    else if (/\.css$/i.test(file)) refs = extractRefsFromCss(await readFile(file, "utf8"));
    else if (/\.json$/i.test(file)) {
      resolveBase = targetDir;
      try {
        refs = extractAssetRefsFromJson(JSON.parse(await readFile(file, "utf8")));
      } catch {
        findings.push(finding("error", "json-parse-error", `${path.relative(targetDir, file)} is not valid JSON`));
        continue;
      }
    } else if (/\.js$/i.test(file)) {
      resolveBase = targetDir; // same reasoning as JSON: a JS string literal has no
      // browser-enforced relative-path rule, and this codebase's own convention
      // (collections.json) is root-relative for exactly this kind of data-shaped ref.
      refs = extractRefsFromJs(await readFile(file, "utf8"));
    } else {
      continue;
    }

    for (const ref of refs.filter(isLocal)) {
      const resolved = path.resolve(resolveBase, ref.split(/[?#]/)[0]);
      referenced.add(resolved);
      if (!existsSync(resolved)) {
        findings.push(
          finding("error", "broken-asset-ref", `${path.relative(targetDir, file)} references \`${ref}\`, which does not resolve`, {
            file: path.relative(targetDir, file),
            ref,
          })
        );
      }
    }
  }

  const assetDirs = config.assetDirs ?? ["links"];
  for (const dirName of assetDirs) {
    const dir = path.join(targetDir, dirName);
    if (!existsSync(dir)) continue;
    const files = (await walk(dir, DEFAULT_EXCLUDE_DIRS)).filter((f) => ASSET_EXT.test(f));
    for (const f of files) {
      if (!referenced.has(path.resolve(f))) {
        findings.push(finding("error", "orphaned-asset", `${path.relative(targetDir, f)} is never referenced`, { file: path.relative(targetDir, f) }));
      }
    }
  }

  return findings;
}

/** VERSION file vs. whatever version-shaped string appears in the rendered banner
 *  text of each page. Deliberately a raw-text check (no browser) — it's checking a
 *  static string in static markup, and the plan places this in the free/ms tier. */
async function checkVersionStamp(targetDir) {
  const findings = [];
  const versionPath = path.join(targetDir, "VERSION");
  if (!existsSync(versionPath)) return findings;
  const version = (await readFile(versionPath, "utf8")).trim();

  const pages = await findPages(targetDir).catch(() => []);
  for (const rel of pages) {
    const html = await readFile(path.join(targetDir, rel), "utf8");
    const bannerMatch = html.match(/\bv(\d+\.\d+(?:\.\d+)?)\b/i);
    if (bannerMatch && bannerMatch[1] !== version) {
      findings.push(
        finding(
          "error",
          "version-stamp-mismatch",
          `VERSION file says ${version}, but ${rel} renders a banner stamped v${bannerMatch[1]}`,
          { page: rel, versionFile: version, banner: bannerMatch[1] }
        )
      );
    }
  }
  return findings;
}

/** A generated `window.NAME = {...};` wrapper (the file:// data-loading pattern)
 *  whose embedded JSON has drifted from the source data/*.json it's supposed to
 *  mirror — e.g. collections.json was edited but the regenerate step wasn't run. */
async function checkDataSync(targetDir, allFiles) {
  const findings = [];
  const dataJsFiles = allFiles.filter((f) => /-data\.js$/.test(f));
  const jsonFiles = allFiles.filter((f) => /\.json$/.test(f) && !f.includes("toolkit-uikit.config.json"));

  for (const jsFile of dataJsFiles) {
    const src = await readFile(jsFile, "utf8");
    const m = src.match(/window\.(\w+)\s*=\s*([\s\S]+?);?\s*$/);
    if (!m) continue;
    let embedded;
    try {
      embedded = JSON.parse(m[2]);
    } catch {
      findings.push(finding("error", "data-js-parse-error", `${path.relative(targetDir, jsFile)} does not contain parseable embedded JSON`));
      continue;
    }
    const stem = path.basename(jsFile).replace(/-data\.js$/, "");
    const match = jsonFiles.find((f) => path.basename(f, ".json") === stem) ?? jsonFiles[0];
    if (!match) continue;
    const source = JSON.parse(await readFile(match, "utf8"));
    if (JSON.stringify(source) !== JSON.stringify(embedded)) {
      findings.push(
        finding(
          "error",
          "data-js-drift",
          `${path.relative(targetDir, jsFile)} does not match ${path.relative(targetDir, match)} — the regenerate step wasn't run after the last edit`,
          { generated: path.relative(targetDir, jsFile), source: path.relative(targetDir, match) }
        )
      );
    }
  }
  return findings;
}

async function checkStrayBackupDirs(targetDir) {
  const findings = [];
  const entries = await walk(targetDir, new Set([".git", "node_modules"]));
  const backupDirNames = new Set();
  for (const f of entries) {
    for (const part of path.relative(targetDir, f).split(path.sep)) {
      if (/^_?backup$|^z_backup$/i.test(part)) backupDirNames.add(part);
    }
  }
  for (const name of backupDirNames) {
    findings.push(
      finding("error", "stray-backup-dir", `a "${name}" directory is committed — that's git's job, not a hand-rolled copy`, { dir: name })
    );
  }
  return findings;
}

// ── Tier 2: rendered, one Playwright pass per page × breakpoint ────────────────

async function checkRendered(targetDir, pages) {
  const findings = [];
  for (const rel of pages) {
    for (const bp of BREAKPOINTS) {
      const { page, blocked, close } = await openPage(targetDir, rel, bp);
      try {
        await forceRevealAll(page);

        for (const req of blocked) {
          findings.push(
            finding(
              "error",
              "external-request",
              `${rel}@${bp.name} requested ${req.url} — breaks any "works offline" claim`,
              { page: rel, breakpoint: bp.name, url: req.url }
            )
          );
        }

        const overflow = await checkHorizontalOverflow(page);
        if (overflow.overflowing) {
          findings.push(
            finding(
              "error",
              "horizontal-overflow",
              `${rel}@${bp.name} content is ${overflow.scrollWidth}px wide in a ${overflow.viewportWidth}px viewport`,
              { page: rel, breakpoint: bp.name, ...overflow }
            )
          );
        }

        const contrastIssues = await checkContrast(page);
        for (const c of contrastIssues) {
          findings.push(
            finding(
              "warning",
              "contrast",
              `${rel}@${bp.name} ${c.selector} "${c.text}" is ${c.ratio}:1 against a ${c.threshold}:1 AA floor (${c.fg} on ${c.bg})`,
              { page: rel, breakpoint: bp.name, ...c }
            )
          );
        }
      } finally {
        await close();
      }
    }
  }
  return findings;
}

// ── Orchestration ───────────────────────────────────────────────────────────────

export async function audit(targetDir, out, { tier1Only = false } = {}) {
  await mkdir(out, { recursive: true });
  const config = await loadConfig(targetDir);
  // Walked once and shared: checkAssetIntegrity previously re-walked independently
  // of checkDocReferencedFiles/checkDataSync, tripling the filesystem traversal for
  // no reason, and each walk had subtly diverging exclude sets. One walk, one
  // exclude policy, one referenced allFiles list.
  const allFiles = await walk(targetDir, DEFAULT_EXCLUDE_DIRS);

  const tier1 = (
    await Promise.all([
      checkDocReferencedFiles(targetDir, allFiles),
      checkAssetIntegrity(targetDir, config, allFiles),
      checkVersionStamp(targetDir),
      checkDataSync(targetDir, allFiles),
      checkStrayBackupDirs(targetDir),
    ])
  ).flat();

  let tier2 = [];
  if (!tier1Only) {
    const pages = await findPages(targetDir);
    tier2 = await checkRendered(targetDir, pages);
  }

  const findings = [...tier1, ...tier2];
  const summary = {
    total: findings.length,
    errors: findings.filter((f) => f.severity === "error").length,
    warnings: findings.filter((f) => f.severity === "warning").length,
    byCheck: Object.fromEntries(
      [...new Set(findings.map((f) => f.check))].map((c) => [c, findings.filter((f) => f.check === c).length])
    ),
  };

  const report = { targetDir, ranAt: new Date().toISOString(), tier1Only, summary, findings };
  await writeFile(path.join(out, "report.json"), JSON.stringify(report, null, 2));
  return report;
}

const isMain = import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
  const { targetDir, out, tier1Only } = parseArgs(process.argv.slice(2));
  const report = await audit(targetDir, out, { tier1Only });
  console.log(`uikit audit: ${report.summary.errors} error(s), ${report.summary.warnings} warning(s) -> ${out}/report.json`);
  for (const f of report.findings) {
    console.log(`  [${f.severity}] ${f.check}: ${f.message}`);
  }
  if (report.summary.errors > 0) process.exit(1);
}
