#!/usr/bin/env node
// Deterministic screenshot capture for a static HTML site/mockup.
//
// Usage:
//   node shoot.mjs <target-dir> [--out <dir>] [--pages a.html,b.html]
//
// Captures every page found (see lib.findPages) at BREAKPOINTS, full-page plus a
// clip per top-level <section>. Writes:
//   <out>/<pageSlug>/<breakpoint>/full.png
//   <out>/<pageSlug>/<breakpoint>/section-<id>.png
//   <out>/manifest.json           — what was captured, for diff.mjs to walk
//   <out>/blocked-requests.json   — every non-file:// request the page attempted;
//                                    empty means the offline claim holds.
//
// Does not judge anything — diff.mjs and audit.mjs read this output and decide
// pass/fail. shoot.mjs's only job is to produce the same pixels every time.

import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { openPage, forceRevealAll, findPages, findSections, BREAKPOINTS, slugifyPage } from "./lib.mjs";

function parseArgs(argv) {
  const [targetDir, ...rest] = argv;
  if (!targetDir) {
    console.error("usage: node shoot.mjs <target-dir> [--out <dir>] [--pages a.html,b.html]");
    process.exit(2);
  }
  let out = path.join(process.cwd(), "uikit-output", "current");
  let pages = null;
  for (let i = 0; i < rest.length; i++) {
    if (rest[i] === "--out") out = rest[++i];
    else if (rest[i] === "--pages") pages = rest[++i].split(",");
  }
  return { targetDir: path.resolve(targetDir), out: path.resolve(out), pages };
}

export async function shoot(targetDir, out, explicitPages = null) {
  const pages = explicitPages ?? (await findPages(targetDir));
  await mkdir(out, { recursive: true });

  const manifest = { targetDir, capturedAt: new Date().toISOString(), pages: [] };
  const allBlocked = {};

  for (const pageRelPath of pages) {
    const slug = slugifyPage(pageRelPath);
    const pageEntry = { pageRelPath, slug, breakpoints: {} };

    for (const bp of BREAKPOINTS) {
      const { page, blocked, close } = await openPage(targetDir, pageRelPath, bp);
      try {
        await forceRevealAll(page);

        const dir = path.join(out, slug, bp.name);
        await mkdir(dir, { recursive: true });

        const fullPath = path.join(dir, "full.png");
        await page.screenshot({ path: fullPath, fullPage: true });

        // Element screenshots (as opposed to a manual viewport-relative `clip`) auto-
        // scroll the target into view first, so this captures sections below the
        // fold correctly regardless of current scroll position. A first version of
        // this used `page.screenshot({clip})`, which does NOT auto-scroll for a
        // non-fullPage capture — every section outside the initial viewport failed
        // silently into the catch block below. Caught only by inspecting real output
        // against the EW mockup: 7 sections found, but 1 screenshot written.
        const sectionLocator = page.locator("section, [data-shoot]");
        const sectionCount = await sectionLocator.count();
        const sectionIds = [];
        const shots = ["full.png"];
        for (let i = 0; i < sectionCount; i++) {
          const el = sectionLocator.nth(i);
          const box = await el.boundingBox();
          if (!box || box.width === 0 || box.height === 0) continue;
          const id = await el.evaluate((node, idx) => node.id || node.getAttribute("data-shoot") || `section-${idx}`, i);
          sectionIds.push(id);
          const file = `section-${id}.png`.replace(/[^a-zA-Z0-9._-]/g, "_");
          try {
            await el.screenshot({ path: path.join(dir, file) });
            shots.push(file);
          } catch {
            // A section can go display:none or detach between measurement and
            // capture on a dynamic page; skip it rather than fail the whole run.
          }
        }

        pageEntry.breakpoints[bp.name] = { shots, sections: sectionIds };
        if (blocked.length > 0) {
          allBlocked[`${pageRelPath}@${bp.name}`] = blocked;
        }
      } finally {
        await close();
      }
    }
    manifest.pages.push(pageEntry);
  }

  await writeFile(path.join(out, "manifest.json"), JSON.stringify(manifest, null, 2));
  await writeFile(path.join(out, "blocked-requests.json"), JSON.stringify(allBlocked, null, 2));

  return { manifest, blocked: allBlocked };
}

const isMain = import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
  const { targetDir, out, pages } = parseArgs(process.argv.slice(2));
  const { manifest, blocked } = await shoot(targetDir, out, pages);
  const shotCount = manifest.pages.reduce(
    (n, p) => n + Object.values(p.breakpoints).reduce((m, b) => m + b.shots.length, 0),
    0
  );
  const blockedCount = Object.values(blocked).reduce((n, arr) => n + arr.length, 0);
  console.log(`uikit shoot: ${manifest.pages.length} pages, ${shotCount} images -> ${out}`);
  if (blockedCount > 0) {
    console.log(`  ! ${blockedCount} external request(s) blocked (offline guarantee violated) — see blocked-requests.json`);
  }
}
