#!/usr/bin/env node
// Compares a "current" screenshot set (from shoot.mjs) against a committed baseline
// set, pixel by pixel. Pure image comparison — no browser involved, so this half of
// the harness is fast and has no Playwright dependency at runtime.
//
// Usage:
//   node diff.mjs <baselineDir> <currentDir> [--out <reportDir>] [--threshold 0.001]
//
// Exit code is non-zero if any image's diff ratio exceeds --threshold (default 0.1%
// of pixels), or if a page/breakpoint/section present in one set is missing from the
// other. That asymmetry matters: a baseline losing a section is exactly the kind of
// silent regression (e.g. content moved and the diff went unnoticed) this exists to catch.

import { writeFile, mkdir, readdir } from "node:fs/promises";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { PNG } from "pngjs";
import pixelmatch from "pixelmatch";

const DEFAULT_THRESHOLD = 0.001; // 0.1% of pixels differing fails the pair

function parseArgs(argv) {
  const [baselineDir, currentDir, ...rest] = argv;
  if (!baselineDir || !currentDir) {
    console.error("usage: node diff.mjs <baselineDir> <currentDir> [--out <dir>] [--threshold 0.001]");
    process.exit(2);
  }
  let out = path.join(process.cwd(), "uikit-output", "diff-report");
  let threshold = DEFAULT_THRESHOLD;
  for (let i = 0; i < rest.length; i++) {
    if (rest[i] === "--out") out = rest[++i];
    else if (rest[i] === "--threshold") threshold = parseFloat(rest[++i]);
  }
  return { baselineDir: path.resolve(baselineDir), currentDir: path.resolve(currentDir), out: path.resolve(out), threshold };
}

async function listPngs(dir) {
  if (!existsSync(dir)) return [];
  const all = await readdir(dir, { recursive: true });
  return all.filter((f) => f.endsWith(".png")).sort();
}

function readPng(filePath) {
  return PNG.sync.read(readFileSync(filePath));
}

export async function diff(baselineDir, currentDir, out, threshold = DEFAULT_THRESHOLD) {
  await mkdir(out, { recursive: true });
  const baselineFiles = new Set(await listPngs(baselineDir));
  const currentFiles = new Set(await listPngs(currentDir));
  const allFiles = new Set([...baselineFiles, ...currentFiles]);

  const pairs = [];
  for (const rel of [...allFiles].sort()) {
    if (!baselineFiles.has(rel)) {
      pairs.push({ path: rel, status: "new", diffRatio: null });
      continue;
    }
    if (!currentFiles.has(rel)) {
      pairs.push({ path: rel, status: "removed", diffRatio: null });
      continue;
    }

    let img1, img2;
    try {
      img1 = readPng(path.join(baselineDir, rel));
      img2 = readPng(path.join(currentDir, rel));
    } catch (e) {
      pairs.push({ path: rel, status: "error", error: String(e) });
      continue;
    }

    if (img1.width !== img2.width || img1.height !== img2.height) {
      pairs.push({
        path: rel,
        status: "regression",
        reason: `size changed ${img1.width}x${img1.height} -> ${img2.width}x${img2.height}`,
        diffRatio: 1,
      });
      continue;
    }

    const { width, height } = img1;
    const diffImg = new PNG({ width, height });
    const diffPixels = pixelmatch(img1.data, img2.data, diffImg.data, width, height, { threshold: 0.1 });
    const diffRatio = diffPixels / (width * height);
    const status = diffRatio > threshold ? "regression" : "match";

    let diffPath = null;
    if (status === "regression") {
      diffPath = path.join(out, rel.replace(/\.png$/, ".diff.png"));
      await mkdir(path.dirname(diffPath), { recursive: true });
      await writeFile(diffPath, PNG.sync.write(diffImg));
    }

    pairs.push({ path: rel, status, diffPixels, totalPixels: width * height, diffRatio, diffPath });
  }

  const summary = {
    total: pairs.length,
    match: pairs.filter((p) => p.status === "match").length,
    regression: pairs.filter((p) => p.status === "regression").length,
    new: pairs.filter((p) => p.status === "new").length,
    removed: pairs.filter((p) => p.status === "removed").length,
    error: pairs.filter((p) => p.status === "error").length,
  };

  const report = { baselineDir, currentDir, threshold, summary, pairs };
  await writeFile(path.join(out, "report.json"), JSON.stringify(report, null, 2));
  await writeFile(path.join(out, "report.html"), renderHtml(report));

  return report;
}

function renderHtml(report) {
  const rows = report.pairs
    .filter((p) => p.status !== "match")
    .map((p) => {
      const badge = { regression: "background:#ffdddd", new: "background:#ddeeff", removed: "background:#fff0cc", error: "background:#ffdddd" }[p.status] || "";
      const ratio = p.diffRatio != null ? `${(p.diffRatio * 100).toFixed(3)}%` : "—";
      return `<tr style="${badge}"><td>${p.status}</td><td>${p.path}</td><td>${ratio}</td><td>${p.reason || p.error || ""}</td></tr>`;
    })
    .join("\n");
  return `<!doctype html><meta charset="utf-8"><title>uikit diff report</title>
<style>body{font:14px system-ui;margin:2rem}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:6px 10px;text-align:left}</style>
<h1>uikit diff report</h1>
<p>baseline: <code>${report.baselineDir}</code><br>current: <code>${report.currentDir}</code><br>threshold: ${report.threshold}</p>
<p>${report.summary.match} match, <b>${report.summary.regression} regression</b>, ${report.summary.new} new, ${report.summary.removed} removed, ${report.summary.error} error — out of ${report.summary.total}</p>
<table><tr><th>status</th><th>path</th><th>diff</th><th>note</th></tr>
${rows || '<tr><td colspan="4">No changes.</td></tr>'}
</table>`;
}

const isMain = import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
  const { baselineDir, currentDir, out, threshold } = parseArgs(process.argv.slice(2));
  const report = await diff(baselineDir, currentDir, out, threshold);
  console.log(
    `uikit diff: ${report.summary.match} match, ${report.summary.regression} regression, ${report.summary.new} new, ${report.summary.removed} removed -> ${out}`
  );
  // "removed" fails alongside "regression"/"error": a baseline image with no
  // current counterpart means content silently disappeared, which is exactly what
  // this tool exists to catch. "new" does not fail on its own — new baseline-less
  // content isn't inherently wrong, it just needs a baseline once reviewed.
  if (report.summary.regression > 0 || report.summary.error > 0 || report.summary.removed > 0) {
    process.exit(1);
  }
}
