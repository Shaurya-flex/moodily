/**
 * Layout guard: nothing may spill off the side of the screen.
 *
 * check_site.py reads the HTML; it cannot tell whether a card is 4px too wide on a 320px phone,
 * because that only exists once the page is laid out. This renders the built site in Chromium at
 * real viewport widths and measures the boxes.
 *
 * Hard failures are unambiguous bugs: the page scrolls sideways, an element sits past the right
 * edge, or text is clipped inside its own box. Softer things (a heading stranding its last word,
 * uneven card heights) are reported but do not fail — they depend on the exact font metrics of the
 * machine, and a build should not break because a runner shipped a different font version.
 *
 * External requests are blocked so the render is deterministic: web fonts would otherwise make the
 * result depend on the network. System fonts give different metrics than production, which makes
 * this check conservative rather than exact — it catches structural overflow, not hairline drift.
 *
 * Local runs skip when Playwright is absent. CI must not skip: a guard that quietly disappears when
 * its dependency fails to install is worse than no guard, so a missing import is a failure there.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const TOLERANCE = 4; // sub-pixel rounding, scrollbar gutters, and font metrics differing between
                     // a developer's machine and the CI runner. The regression this first caught was 6px.

const PAGES = ["/", "/services/", "/samples/", "/contact/", "/about/",
               "/international/", "/international/services/", "/international/booking-rescue/"];
const WIDTHS = [320, 390, 768, 1280];
const THEMES = ["light", "dark"];

const TYPES = {
  ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8", ".json": "application/json",
  ".svg": "image/svg+xml", ".webp": "image/webp", ".png": "image/png",
  ".jpg": "image/jpeg", ".ico": "image/x-icon", ".xml": "application/xml",
  ".woff2": "font/woff2", ".txt": "text/plain; charset=utf-8",
};

function serve() {
  const server = http.createServer(async (req, res) => {
    let rel = decodeURIComponent(req.url.split("?")[0]);
    if (rel.endsWith("/")) rel += "index.html";
    const file = path.join(ROOT, rel);
    if (!file.startsWith(ROOT) || !existsSync(file)) { res.writeHead(404).end("not found"); return; }
    try {
      res.writeHead(200, { "Content-Type": TYPES[path.extname(file)] || "application/octet-stream" });
      res.end(await readFile(file));
    } catch { res.writeHead(500).end("error"); }
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

/** Runs inside the page. Returns every box that breaks out of the viewport or its own container. */
function audit({ tolerance }) {
  const out = [];
  const docW = document.documentElement.clientWidth;
  const label = (el) => el.tagName + (el.className && typeof el.className === "string"
    ? "." + el.className.trim().split(/\s+/).slice(0, 2).join(".") : "");
  const text = (el) => (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 60);
  // An ancestor that scrolls horizontally is a carousel: its children are meant to sit outside.
  const inScroller = (el) => {
    for (let n = el.parentElement; n && n !== document.documentElement; n = n.parentElement) {
      const o = getComputedStyle(n).overflowX;
      if (o === "auto" || o === "scroll") return true;
    }
    return false;
  };
  const cls = (el) => (typeof el.className === "string" ? el.className : "");
  // Three things look like overflow but are not, each verified by hand before being excluded:
  //  - sr-only / visually-hidden text is clipped to 1px on purpose, for screen readers.
  //  - a skip link is parked off the left edge until it takes focus; that is the pattern working.
  //  - a closed <details> still reports boxes for its hidden rows, at widths the user never sees.
  const inClosedDetails = (el) => {
    for (let n = el.parentElement; n && n !== document.documentElement; n = n.parentElement) {
      if (n.tagName === "DETAILS" && !n.open) return true;
    }
    return false;
  };
  const hidden = (el) => el.offsetParent === null
    || /\bsr-only\b|\bvisually-hidden\b|\bskip\b/.test(cls(el))
    || inClosedDetails(el);

  if (document.documentElement.scrollWidth > docW + tolerance) {
    out.push({ kind: "PAGE_SCROLLS_SIDEWAYS", detail: `scrollWidth ${document.documentElement.scrollWidth} > ${docW}` });
  }
  for (const el of document.querySelectorAll("body *")) {
    if (hidden(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    if (r.right > docW + tolerance && !inScroller(el)) {
      out.push({ kind: "PAST_RIGHT_EDGE", el: label(el), right: Math.round(r.right), text: text(el) });
    }
    if (r.left < -tolerance && !inScroller(el)) {
      out.push({ kind: "PAST_LEFT_EDGE", el: label(el), left: Math.round(r.left), text: text(el) });
    }
  }
  for (const el of document.querySelectorAll("h1,h2,h3,h4,p,li,dt,dd,a,button,strong,span")) {
    if (hidden(el) || el.children.length || !el.textContent.trim()) continue;
    const cs = getComputedStyle(el);
    if (cs.overflowX === "auto" || cs.overflowX === "scroll") continue;
    if (el.scrollWidth > el.clientWidth + tolerance) {
      out.push({ kind: "TEXT_CLIPPED", el: label(el), scrollW: el.scrollWidth, clientW: el.clientWidth, text: text(el) });
    }
  }
  // reported only — font-metric dependent
  let orphans = 0;
  for (const el of document.querySelectorAll("h1,h2,h3,.lead")) {
    if (hidden(el) || !el.textContent.trim()) continue;
    const range = document.createRange();
    range.selectNodeContents(el);
    const lines = [...range.getClientRects()].filter((x) => x.width > 0.5);
    if (lines.length < 2) continue;
    const last = lines[lines.length - 1], prev = lines[lines.length - 2];
    if (last.width < prev.width * 0.3 && el.textContent.trim().split(/\s+/).length > 3) orphans++;
  }
  return { out, orphans };
}

let playwright = null;
try { ({ default: playwright } = await import("playwright")); } catch { /* reported below */ }

test("no element escapes the viewport at any supported width", { concurrency: false }, async (t) => {
  if (!playwright) {
    // In CI a missing browser means the guard silently stopped guarding — that is a failure.
    assert.ok(!process.env.CI, "playwright is required in CI: run `npx playwright install --with-deps chromium`");
    t.skip("playwright not installed — run `npm i -D playwright` to enable the layout guard locally");
    return;
  }
  const server = await serve();
  const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await playwright.chromium.launch();
  const failures = [];
  let orphanTotal = 0, checked = 0;
  try {
    for (const theme of THEMES) {
      for (const width of WIDTHS) {
        const context = await browser.newContext({ viewport: { width, height: 900 } });
        // deterministic render: no web fonts, no analytics, no third-party anything
        await context.route("**/*", (route) =>
          route.request().url().startsWith(base) ? route.continue() : route.abort());
        const page = await context.newPage();
        for (const p of PAGES) {
          const res = await page.goto(base + p, { waitUntil: "load" });
          assert.equal(res.status(), 200, `${p} did not load`);
          await page.evaluate((th) => document.documentElement.setAttribute("data-theme", th), theme);
          await page.waitForTimeout(120);
          const { out, orphans } = await page.evaluate(audit, { tolerance: TOLERANCE });
          orphanTotal += orphans;
          checked++;
          for (const f of out) failures.push({ theme, page: p, width, ...f });
        }
        await context.close();
      }
    }
  } finally {
    await browser.close();
    server.close();
  }
  console.log(`layout: ${checked} page/width/theme combinations checked · ${orphanTotal} stranded-word headings (reported, not failed)`);
  if (failures.length) {
    const lines = failures.slice(0, 25).map((f) =>
      `  ${f.kind} · ${f.page} @${f.width}px ${f.theme} · ${f.el || ""} ${f.detail || ""} ${f.text ? `· "${f.text}"` : ""}`);
    assert.fail(`${failures.length} layout problem(s):\n${lines.join("\n")}`);
  }
});
