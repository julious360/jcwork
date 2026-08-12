// Shared engine for the uikit harness: deterministic page capture, asset-reference
// resolution, and the WCAG contrast check. Every CLI (shoot/diff/audit/gate) builds on
// this rather than duplicating Playwright setup.
//
// Determinism matters more than realism here. A verification harness that reports
// false regressions gets ignored; one that silently passes real ones is worse. Two
// things are load-bearing and were found by actually rendering a real page, not by
// assumption:
//   1. `reducedMotion: 'reduce'` is mandatory. The EastWest mockup reveals every
//      below-fold section via `.reveal { opacity: 0 }` + IntersectionObserver
//      (html/assets/campaign.css:696, campaign.js:206). A static capture never
//      scrolls, so without this every section below the fold captures blank.
//   2. Every non-file:// request must be blocked and logged, not merely ignored.
//      A mockup can promise "no internet needed" while quietly fetching Google
//      Fonts; the block log is also the audit evidence for that claim.

import { chromium } from "playwright-core";
import { readFile, readdir, stat } from "node:fs/promises";
import { existsSync } from "node:fs";
import { execSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

/** Locate a Chromium/Chrome binary this session can launch. playwright-core (as
 *  opposed to the full `playwright` package) never downloads or manages a browser
 *  itself — it only drives one you point it at via executablePath — so this has to
 *  find one. Checked in order: an explicit override, this original environment's
 *  preinstalled Chromium (kept first so nothing changes for sessions already using
 *  it), then the common install locations for each OS. First one that exists wins.
 *  This matters concretely: the original hardcoded path
 *  (/opt/pw-browsers/chromium-1194/...) is specific to the cloud container this
 *  toolkit was built in and does not exist on a downloaded copy run locally on
 *  Windows/macOS — without this, every command would fail immediately with an
 *  unhelpful "executable doesn't exist" error on first use outside that container. */
function findChromium() {
  const candidates = [
    process.env.UIKIT_CHROMIUM_PATH,
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    // Windows
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    // macOS
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    // Linux
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/snap/bin/chromium",
  ].filter(Boolean);

  for (const c of candidates) {
    if (existsSync(c)) return c;
  }

  // Last resort: ask the OS to resolve a common binary name on PATH.
  const onPath = ["google-chrome", "chromium", "chromium-browser", "chrome"];
  const finder = process.platform === "win32" ? "where" : "which";
  for (const name of onPath) {
    try {
      const found = execSync(`${finder} ${name}`, { stdio: ["ignore", "pipe", "ignore"] })
        .toString()
        .split(/\r?\n/)[0]
        .trim();
      if (found && existsSync(found)) return found;
    } catch {
      /* not found on PATH, try the next name */
    }
  }

  throw new Error(
    "No Chrome/Chromium binary found. Install Google Chrome or Chromium, or set " +
      "UIKIT_CHROMIUM_PATH to its executable path."
  );
}

export const CHROMIUM_PATH = findChromium();

export const BREAKPOINTS = [
  { name: "390", width: 390, height: 844 },
  { name: "834", width: 834, height: 1112 },
  { name: "1440", width: 1440, height: 900 },
];

// Freezing the clock kills caret blink and any Date-driven animation; a fixed
// arbitrary instant is enough since nothing under test reads wall-clock time.
const FROZEN_TIME = "2026-01-01T12:00:00Z";

/** Find HTML pages to capture. Respects <target>/toolkit-uikit.config.json { "pages": [...] }
 *  if present; otherwise looks in html/*.html (the EW-style layout), falling back to
 *  *.html at the target root, excluding any _backup directory. */
export async function findPages(targetDir) {
  const configPath = path.join(targetDir, "toolkit-uikit.config.json");
  if (existsSync(configPath)) {
    const config = JSON.parse(await readFile(configPath, "utf8"));
    if (Array.isArray(config.pages) && config.pages.length > 0) return config.pages;
  }
  const htmlDir = path.join(targetDir, "html");
  const candidates = existsSync(htmlDir) ? htmlDir : targetDir;
  const rel = path.relative(targetDir, candidates);
  const entries = await readdir(candidates, { withFileTypes: true });
  return entries
    .filter((e) => e.isFile() && e.name.endsWith(".html"))
    .map((e) => path.join(rel, e.name))
    .sort();
}

/** Every non-file:// request is aborted and logged. This *is* the offline-guarantee
 *  audit: a page that claims to need no internet connection should never produce
 *  an entry here. */
function installRequestBlocking(page, blocked) {
  page.route("**/*", (route) => {
    const url = route.request().url();
    if (url.startsWith("file:")) {
      route.continue();
      return;
    }
    blocked.push({ url, resourceType: route.request().resourceType() });
    route.abort();
  });
}

/** Launch a page against one file:// target with deterministic capture settings.
 *  Caller must call `close()` when done. Returns { browser, page, blocked }, where
 *  `blocked` accumulates external-request log entries as the page runs. */
export async function openPage(targetDir, pageRelPath, breakpoint, { forceReducedMotion = true } = {}) {
  const browser = await chromium.launch({
    executablePath: CHROMIUM_PATH,
    args: ["--no-sandbox", "--disable-gpu", "--hide-scrollbars", "--force-color-profile=srgb"],
  });
  const context = await browser.newContext({
    viewport: { width: breakpoint.width, height: breakpoint.height },
    reducedMotion: forceReducedMotion ? "reduce" : "no-preference",
    colorScheme: "light",
  });
  await context.clock.install({ time: FROZEN_TIME });

  const page = await context.newPage();
  const blocked = [];
  installRequestBlocking(page, blocked);

  const fileUrl = pathToFileURL(path.resolve(targetDir, pageRelPath)).href;
  await page.goto(fileUrl, { waitUntil: "load" });

  // Give in-page IntersectionObservers (scroll-reveal, lazy sections) a beat to
  // fire even though reducedMotion already made their CSS transition instant.
  await page.evaluate(() =>
    new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))
  );

  return {
    browser,
    page,
    blocked,
    async close() {
      await browser.close();
    },
  };
}

/** Scroll every element into view once, so IntersectionObserver-gated content (the
 *  scroll-reveal pattern) has actually triggered before a full-page screenshot,
 *  independent of the reducedMotion CSS fallback. Belt-and-suspenders: reducedMotion
 *  is the documented, intentional escape hatch (campaign.css:698); this is a second,
 *  independent guarantee for markup that reveals via JS state rather than CSS media. */
export async function forceRevealAll(page) {
  await page.evaluate(async () => {
    const height = document.documentElement.scrollHeight;
    const step = Math.max(200, Math.floor(window.innerHeight / 2));
    for (let y = 0; y < height; y += step) {
      window.scrollTo(0, y);
      await new Promise((r) => requestAnimationFrame(r));
    }
    window.scrollTo(0, 0);
    // Also force-clear any element still holding opacity:0 / a reveal-pending class,
    // in case an observer never fired (e.g. content added after our scroll pass).
    document.querySelectorAll(".reveal:not(.visible)").forEach((el) => el.classList.add("visible"));
  });
}

/** Bounding boxes for top-level <section> elements (or [data-shoot] opt-ins), for
 *  per-section clipped captures in addition to the full-page shot. */
export async function findSections(page) {
  return page.evaluate(() => {
    const nodes = Array.from(document.querySelectorAll("section, [data-shoot]"));
    return nodes
      .map((el, i) => {
        const rect = el.getBoundingClientRect();
        const id = el.id || el.getAttribute("data-shoot") || `section-${i}`;
        return { id, x: rect.x, y: rect.y + window.scrollY, width: rect.width, height: rect.height };
      })
      .filter((s) => s.width > 0 && s.height > 0);
  });
}

/** WCAG 2.x contrast check, implemented directly (no axe-core dependency) against
 *  computed styles. Walks visible text nodes, resolves the effective background by
 *  walking ancestors for the first non-transparent fill, and flags ratios below the
 *  AA threshold (4.5:1 normal text, 3:1 for large text >=24px or >=18.66px bold). */
export async function checkContrast(page) {
  return page.evaluate(() => {
    function parseColor(str) {
      const m = str.match(/rgba?\(([^)]+)\)/);
      if (!m) return null;
      const parts = m[1].split(",").map((s) => parseFloat(s.trim()));
      return { r: parts[0], g: parts[1], b: parts[2], a: parts.length > 3 ? parts[3] : 1 };
    }
    function relLuminance({ r, g, b }) {
      const lin = (c) => {
        const s = c / 255;
        return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
      };
      return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
    }
    function contrastRatio(fg, bg) {
      const l1 = relLuminance(fg) + 0.05;
      const l2 = relLuminance(bg) + 0.05;
      return l1 > l2 ? l1 / l2 : l2 / l1;
    }
    function effectiveBackground(el) {
      let node = el;
      while (node) {
        const bg = parseColor(getComputedStyle(node).backgroundColor);
        if (bg && bg.a > 0.01) return bg;
        node = node.parentElement;
      }
      return { r: 255, g: 255, b: 255, a: 1 }; // documents default to a white canvas
    }

    const results = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
    let el;
    while ((el = walker.nextNode())) {
      const hasOwnText = Array.from(el.childNodes).some(
        (n) => n.nodeType === Node.TEXT_NODE && n.textContent.trim().length > 0
      );
      if (!hasOwnText) continue;
      const style = getComputedStyle(el);
      if (style.visibility === "hidden" || style.display === "none") continue;
      const opacity = parseFloat(style.opacity);
      if (opacity < 0.05) continue; // treat near-invisible as a contrast failure elsewhere, not here
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) continue;

      const fg = parseColor(style.color);
      if (!fg) continue;
      const bg = effectiveBackground(el);
      const ratio = contrastRatio(fg, bg);

      const size = parseFloat(style.fontSize);
      const weight = parseInt(style.fontWeight, 10) || 400;
      const isLarge = size >= 24 || (size >= 18.66 && weight >= 700);
      const threshold = isLarge ? 3.0 : 4.5;

      if (ratio < threshold) {
        results.push({
          selector: el.tagName.toLowerCase() + (el.id ? `#${el.id}` : "") + (el.className && typeof el.className === "string" ? `.${el.className.trim().split(/\s+/).join(".")}` : ""),
          text: el.textContent.trim().slice(0, 60),
          ratio: Math.round(ratio * 100) / 100,
          threshold,
          fg: style.color,
          bg: `rgb(${bg.r}, ${bg.g}, ${bg.b})`,
        });
      }
    }
    return results;
  });
}

/** Horizontal overflow at the current viewport — any element wider than the
 *  document, which forces an unwanted horizontal scrollbar. */
export async function checkHorizontalOverflow(page) {
  return page.evaluate(() => {
    const docWidth = document.documentElement.clientWidth;
    return document.documentElement.scrollWidth > docWidth + 1
      ? { overflowing: true, scrollWidth: document.documentElement.scrollWidth, viewportWidth: docWidth }
      : { overflowing: false };
  });
}

export function slugifyPage(pageRelPath) {
  return pageRelPath.replace(/[\\/]/g, "__").replace(/\.html?$/, "");
}
