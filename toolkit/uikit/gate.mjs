#!/usr/bin/env node
// The pre-handoff gate: nothing ships unreviewed. One command, fail-closed, cheap
// tiers run before expensive ones so a broken build never pays for a full render.
//
//   Tier 1 — static audit checks           (ms)
//   Tier 2 — rendered audit checks         (~15s, only if Tier 1 is clean)
//   Tier 3 — visual diff against baseline  (only if Tiers 1-2 are clean)
//
// Usage:
//   node gate.mjs <target-dir> [--out <dir>] [--update-baseline]
//
// Exit code is non-zero on ANY finding from Tiers 1-2 — including "warning"
// severity findings like contrast, which audit.mjs alone treats as non-fatal.
// That's a deliberate, stricter bar for this specific consumer: audit.mjs run ad
// hoc is a diagnostic tool a person reads and judges; the gate is what decides
// whether a build is allowed to leave as a deliverable, and at that point a
// contrast failure is not something to silently wave through.
//
// --update-baseline shoots fresh screenshots and makes them the new baseline
// instead of diffing against the old one. Nothing else in this tool writes to the
// baseline directory, so a baseline only ever changes when a human runs this flag
// on purpose.

import { mkdir, cp, rm } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { audit } from "./audit.mjs";
import { shoot } from "./shoot.mjs";
import { diff } from "./diff.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));

function parseArgs(argv) {
  const [targetDir, ...rest] = argv;
  if (!targetDir) {
    console.error("usage: node gate.mjs <target-dir> [--out <dir>] [--update-baseline]");
    process.exit(2);
  }
  let out = path.join(process.cwd(), "uikit-output", "gate");
  let updateBaseline = false;
  for (let i = 0; i < rest.length; i++) {
    if (rest[i] === "--out") out = rest[++i];
    else if (rest[i] === "--update-baseline") updateBaseline = true;
  }
  return { targetDir: path.resolve(targetDir), out: path.resolve(out), updateBaseline };
}

function slug(targetDir) {
  return path.basename(targetDir).replace(/[^a-zA-Z0-9._-]/g, "_");
}

export async function gate(targetDir, out, { updateBaseline = false } = {}) {
  await mkdir(out, { recursive: true });
  const baselineDir = path.join(HERE, "baselines", slug(targetDir));
  const result = { targetDir, ranAt: new Date().toISOString(), tiers: {} };

  // Tier 1: static-only first, cheap enough (<1s, verified) that re-running it
  // inside the Tier 1+2 combined call below costs nothing, but it lets a broken
  // build fail before a single browser launches.
  console.log("uikit gate: tier 1 (static)…");
  const tier1 = await audit(targetDir, path.join(out, "audit-tier1"), { tier1Only: true });
  result.tiers.tier1 = { errors: tier1.summary.errors, warnings: tier1.summary.warnings };
  if (tier1.summary.errors > 0) {
    result.pass = false;
    result.failedAt = "tier1";
    result.findings = tier1.findings;
    return finish(result, out);
  }

  // Tier 2: full audit (re-runs tier 1's checks; negligible next to a Playwright
  // launch, and keeps audit.mjs as the single implementation of every check).
  console.log("uikit gate: tier 2 (rendered)…");
  const full = await audit(targetDir, path.join(out, "audit-full"), { tier1Only: false });
  result.tiers.tier2 = { errors: full.summary.errors, warnings: full.summary.warnings };
  // Stricter than audit.mjs's own exit policy: warnings block the gate too.
  if (full.summary.errors > 0 || full.summary.warnings > 0) {
    result.pass = false;
    result.failedAt = "tier2";
    result.findings = full.findings;
    return finish(result, out);
  }

  // Tier 3: visual diff against the committed baseline.
  console.log("uikit gate: tier 3 (visual diff)…");
  const currentDir = path.join(out, "current");
  await shoot(targetDir, currentDir);

  if (updateBaseline) {
    await rm(baselineDir, { recursive: true, force: true });
    await mkdir(path.dirname(baselineDir), { recursive: true });
    await cp(currentDir, baselineDir, { recursive: true });
    result.tiers.tier3 = { status: "baseline-updated", baselineDir };
    result.pass = true;
    return finish(result, out);
  }

  if (!existsSync(baselineDir)) {
    result.tiers.tier3 = { status: "no-baseline" };
    result.pass = true; // nothing to compare against yet — not a failure, but flagged
    result.note = `No baseline at ${baselineDir}. Run with --update-baseline to establish one.`;
    return finish(result, out);
  }

  const diffReport = await diff(baselineDir, currentDir, path.join(out, "diff"));
  result.tiers.tier3 = { status: "compared", summary: diffReport.summary };
  const failing = diffReport.summary.regression > 0 || diffReport.summary.removed > 0 || diffReport.summary.error > 0;
  result.pass = !failing;
  if (failing) {
    result.failedAt = "tier3";
    result.diffPairs = diffReport.pairs.filter((p) => p.status !== "match");
  }
  return finish(result, out);
}

async function finish(result, out) {
  const { writeFile } = await import("node:fs/promises");
  await writeFile(path.join(out, "gate-report.json"), JSON.stringify(result, null, 2));
  return result;
}

const isMain = import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
  const { targetDir, out, updateBaseline } = parseArgs(process.argv.slice(2));
  const result = await gate(targetDir, out, { updateBaseline });

  if (result.pass) {
    console.log(`uikit gate: PASS${result.note ? " — " + result.note : ""}`);
    process.exit(0);
  } else {
    console.log(`uikit gate: FAIL at ${result.failedAt}`);
    if (result.findings) {
      for (const f of result.findings) console.log(`  [${f.severity}] ${f.check}: ${f.message}`);
    }
    if (result.diffPairs) {
      for (const p of result.diffPairs) console.log(`  [${p.status}] ${p.path}`);
    }
    console.log(`full report: ${path.join(out, "gate-report.json")}`);
    process.exit(1);
  }
}
