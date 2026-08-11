#!/usr/bin/env node
// The end-of-day pass: find and correct small, safe, reversible issues before they
// pile up, and surface everything else in a digest a person reads once a day
// instead of discovering at hand-off.
//
// Usage:
//   node eod.mjs [repo-root] [--check dir1,dir2,...] [--out <dir>]
//
// SCOPE, DELIBERATELY NARROW:
//
// Auto-fixed, each its own local commit, NEVER pushed: ruff --fix/format on
// <repo-root>/agent+tests (this tool's home repo layout); for any subdirectory of
// repo-root that looks like a "site" (has a VERSION file) — sync its on-page version
// banner to VERSION, regenerate a drifted *-data.js from its source JSON, delete
// orphaned assets. All of these are auto-fixable because they're mechanical and
// reversible: the "correct" value is unambiguous (VERSION file, source JSON, "is
// anything pointing at this file") and every fix is one git revert away.
//
// Reported only, NEVER auto-changed: mypy errors, every Tier 2 finding (contrast,
// overflow, external-request), and — this is the important one — every visual diff
// against a baseline. An earlier draft of this tool's spec listed "re-shoot baselines
// for pages whose markup changed" as auto-fixable, which directly contradicts
// listing "layout regressions" as report-only one line later in the same spec:
// silently overwriting a visual baseline on any diff would defeat the entire purpose
// of visual regression testing (nothing would ever look "broken" once broken). This
// resolves that contradiction in favor of safety: no baseline update is ever
// automatic. `gate.mjs --update-baseline` remains a human-run command.
//
// --check <dirs>: additional, read-only target directories (e.g. a checkout this
// session cannot push to) included in the same daily digest. Every finding for a
// --check target goes to needs-you unconditionally — no fix is ever attempted
// against a directory this tool didn't establish write access to itself.

import { readFile, writeFile, mkdir, readdir, rm } from "node:fs/promises";
import { existsSync } from "node:fs";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import path from "node:path";
import { audit } from "./audit.mjs";
import { gate } from "./gate.mjs";

const run = promisify(execFile);

function parseArgs(argv) {
  let repoRoot = process.cwd();
  let checkDirs = [];
  let out = null;
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--check") checkDirs = argv[++i].split(",").filter(Boolean).map((d) => path.resolve(d));
    else if (argv[i] === "--out") out = argv[++i];
    else rest.push(argv[i]);
  }
  if (rest[0]) repoRoot = path.resolve(rest[0]);
  return { repoRoot, checkDirs, out: out ? path.resolve(out) : path.join(repoRoot, "toolkit", "uikit-output", "eod") };
}

async function gitCommit(repoRoot, files, message) {
  const { stdout: status } = await run("git", ["status", "--porcelain", ...files], { cwd: repoRoot });
  if (!status.trim()) return null;
  await run("git", ["add", ...files], { cwd: repoRoot });
  await run("git", ["commit", "-m", message], { cwd: repoRoot });
  const { stdout: sha } = await run("git", ["rev-parse", "--short", "HEAD"], { cwd: repoRoot });
  return sha.trim();
}

// ── Python auto-fix (this repo's own layout) ────────────────────────────────────

async function autoFixPython(repoRoot) {
  const pyDirs = ["agent", "tests"].filter((d) => existsSync(path.join(repoRoot, d)));
  if (pyDirs.length === 0) return { fixed: [], commit: null, mypyErrors: [] };

  try {
    await run("python3", ["-m", "ruff", "check", "--fix", ...pyDirs], { cwd: repoRoot });
  } catch {
    /* ruff exits non-zero on unfixable findings; format still worth running */
  }
  await run("python3", ["-m", "ruff", "format", ...pyDirs], { cwd: repoRoot }).catch(() => {});

  const commit = await gitCommit(repoRoot, pyDirs, "eod: auto-fix ruff lint/format");

  let mypyErrors = [];
  try {
    await run("python3", ["-m", "mypy", "agent"], { cwd: repoRoot });
  } catch (e) {
    mypyErrors = (e.stdout || "").split("\n").filter((l) => l.includes("error:"));
  }

  return { fixed: commit ? pyDirs : [], commit, mypyErrors };
}

// ── Site discovery (writable subdirectories of repo-root only) ─────────────────

async function discoverSites(repoRoot) {
  const sites = [];
  let entries;
  try {
    entries = await readdir(repoRoot, { withFileTypes: true });
  } catch {
    return sites;
  }
  for (const e of entries) {
    if (!e.isDirectory() || e.name === "node_modules" || e.name === ".git") continue;
    if (existsSync(path.join(repoRoot, e.name, "VERSION"))) sites.push(path.join(repoRoot, e.name));
  }
  return sites;
}

// ── Safe, mechanical site fixes ─────────────────────────────────────────────────

async function fixVersionStamp(siteDir, findings) {
  const fixed = [];
  for (const f of findings.filter((x) => x.check === "version-stamp-mismatch")) {
    const pagePath = path.join(siteDir, f.page);
    const html = await readFile(pagePath, "utf8");
    const re = /\bv(\d+\.\d+(?:\.\d+)?)\b/i;
    if (!re.test(html)) continue;
    await writeFile(pagePath, html.replace(re, `v${f.versionFile}`));
    fixed.push(f.page);
  }
  return fixed;
}

async function fixDataDrift(siteDir, findings) {
  const fixed = [];
  for (const f of findings.filter((x) => x.check === "data-js-drift")) {
    const jsPath = path.join(siteDir, f.generated);
    const jsonPath = path.join(siteDir, f.source);
    const src = await readFile(jsPath, "utf8");
    const nameMatch = src.match(/window\.(\w+)\s*=/);
    if (!nameMatch) continue;
    const json = await readFile(jsonPath, "utf8");
    await writeFile(jsPath, `window.${nameMatch[1]} = ${json.trim()};\n`);
    fixed.push(f.generated);
  }
  return fixed;
}

async function fixOrphans(siteDir, findings) {
  const fixed = [];
  for (const f of findings.filter((x) => x.check === "orphaned-asset")) {
    const filePath = path.join(siteDir, f.file);
    if (existsSync(filePath)) {
      await rm(filePath);
      fixed.push(f.file);
    }
  }
  return fixed;
}

async function autoFixSite(siteDir) {
  const tmpAuditDir = path.join(siteDir, ".eod-tmp-audit");
  const report = await audit(siteDir, tmpAuditDir, { tier1Only: true });
  await rm(tmpAuditDir, { recursive: true, force: true });

  const fixedVersion = await fixVersionStamp(siteDir, report.findings);
  const fixedData = await fixDataDrift(siteDir, report.findings);
  const fixedOrphans = await fixOrphans(siteDir, report.findings);
  const allFixed = [...fixedVersion, ...fixedData, ...fixedOrphans];

  let commit = null;
  if (allFixed.length > 0) {
    commit = await gitCommit(siteDir, allFixed, "eod: sync version stamp / regenerate data / remove orphaned assets");
  }

  const fixedChecks = new Set(["version-stamp-mismatch", "data-js-drift", "orphaned-asset"]);
  const needsYou = report.findings.filter((f) => !fixedChecks.has(f.check) || (fixedChecks.has(f.check) && !commit));

  return { siteDir, fixed: { version: fixedVersion, data: fixedData, orphans: fixedOrphans, commit }, needsYou };
}

// ── Read-only external targets ──────────────────────────────────────────────────

async function checkOnly(targetDir, out) {
  const result = await gate(targetDir, path.join(out, path.basename(targetDir)), { updateBaseline: false });
  const findings = result.findings ?? [];
  const diffFindings = (result.diffPairs ?? []).map((p) => ({
    severity: "warning",
    check: "visual-diff",
    message: `${p.path}: ${p.status}`,
  }));
  return { targetDir, pass: result.pass, needsYou: [...findings, ...diffFindings] };
}

// ── Digest ───────────────────────────────────────────────────────────────────────

function renderDigest(date, pyResult, siteResults, checkResults) {
  const lines = [`# End-of-day report — ${date}`, ""];
  const allFixed = [
    ...(pyResult.commit ? [`ruff lint/format (${pyResult.commit})`] : []),
    ...siteResults.flatMap((s) =>
      s.fixed.commit
        ? [
            `${path.basename(s.siteDir)}: ${[...s.fixed.version.map((v) => `version stamp in ${v}`), ...s.fixed.data.map((d) => `regenerated ${d}`), ...s.fixed.orphans.map((o) => `removed orphan ${o}`)].join(", ")} (${s.fixed.commit})`,
          ]
        : []
    ),
  ];
  const allNeedsYou = [
    ...pyResult.mypyErrors.map((e) => ({ severity: "error", check: "mypy", message: e })),
    ...siteResults.flatMap((s) => s.needsYou.map((f) => ({ ...f, source: path.basename(s.siteDir) }))),
    ...checkResults.flatMap((c) => c.needsYou.map((f) => ({ ...f, source: `${path.basename(c.targetDir)} (read-only)` }))),
  ];

  if (allFixed.length === 0 && allNeedsYou.length === 0) {
    lines.push("Clean run — nothing fixed, nothing needing attention.");
    return lines.join("\n") + "\n";
  }

  lines.push(`## Fixed (${allFixed.length})`, "");
  lines.push(...(allFixed.length ? allFixed.map((f) => `- ${f}`) : ["- none"]), "");

  lines.push(`## Needs you (${allNeedsYou.length})`, "");
  if (allNeedsYou.length === 0) {
    lines.push("- none");
  } else {
    for (const f of allNeedsYou) {
      lines.push(`- [${f.severity}] ${f.source ? `${f.source}: ` : ""}${f.check}: ${f.message}`);
    }
  }
  lines.push("");
  return lines.join("\n") + "\n";
}

// ── Orchestration ───────────────────────────────────────────────────────────────

export async function eod(repoRoot, { checkDirs = [], out } = {}) {
  await mkdir(out, { recursive: true });

  const pyResult = await autoFixPython(repoRoot);
  const sites = await discoverSites(repoRoot);
  const siteResults = [];
  for (const site of sites) siteResults.push(await autoFixSite(site));

  const checkResults = [];
  for (const dir of checkDirs) checkResults.push(await checkOnly(dir, out));

  const date = new Date().toISOString().slice(0, 10);
  const digest = renderDigest(date, pyResult, siteResults, checkResults);

  const reportsDir = path.join(repoRoot, "toolkit", "reports");
  await mkdir(reportsDir, { recursive: true });
  const reportPath = path.join(reportsDir, `${date}.md`);
  await writeFile(reportPath, digest);
  const digestCommit = await gitCommit(repoRoot, [path.relative(repoRoot, reportPath)], `eod: ${date} digest`);

  return { date, reportPath, digestCommit, pyResult, siteResults, checkResults, digest };
}

const isMain = import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
  const { repoRoot, checkDirs, out } = parseArgs(process.argv.slice(2));
  const result = await eod(repoRoot, { checkDirs, out });
  console.log(result.digest);
  console.log(`-> ${result.reportPath}${result.digestCommit ? ` (${result.digestCommit})` : ""}`);
}
