/**
 * Measure every <text> in the generated Instagram posts and fail if any of it escapes the card.
 *
 * social_posts.py breaks lines from an estimated character width, which is a guess — especially
 * for Devanagari, where glyph advances differ from Latin at the same font-size. This renders each
 * SVG in Chromium and measures the real boxes, the same way tests/layout.test.mjs does for pages.
 *
 * Deliberately NOT part of CI: the runner has no guarantee of a Devanagari font, so the metrics
 * there would be a different font's metrics and the result would be meaningless. Run it locally
 * after regenerating:   node scripts/check_social.mjs
 */
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import playwright from "playwright";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DIR = path.join(ROOT, "assets", "img", "social");
const W = 1080, H = 1350, MARGIN = 70, TOL = 3;

const files = (await readdir(DIR)).filter((f) => f.endsWith(".svg")).sort();
const browser = await playwright.chromium.launch();
const page = await browser.newPage({ viewport: { width: W, height: H } });
let bad = 0, smallest = Infinity, smallestWhere = "";

for (const f of files) {
  const svg = await readFile(path.join(DIR, f), "utf8");
  await page.setContent(`<body style="margin:0">${svg}</body>`);
  await page.waitForTimeout(60);
  const rows = await page.evaluate(({ W, H, MARGIN, TOL }) => {
    const out = [];
    const boxes = [];
    for (const el of document.querySelectorAll("text")) {
      const b = el.getBoundingClientRect();
      const txt = (el.textContent || "").slice(0, 46);
      const size = parseFloat(getComputedStyle(el).fontSize);
      // The card has a 76px gutter. Anything closer than MARGIN is either off the card or
      // crowding the edge in a way that reads as a mistake in the feed.
      if (b.right > W - MARGIN + TOL) out.push({ kind: "RIGHT", v: Math.round(b.right), txt, size });
      if (b.left < MARGIN - TOL) out.push({ kind: "LEFT", v: Math.round(b.left), txt, size });
      if (b.bottom > H - MARGIN + TOL) out.push({ kind: "BOTTOM", v: Math.round(b.bottom), txt, size });
      if (b.top < TOL) out.push({ kind: "TOP", v: Math.round(b.top), txt, size });
      out.push({ kind: "SIZE", v: size, txt });
      boxes.push({ b, txt });
    }
    // Two lines of text sharing vertical space means a block ran into the one below it —
    // the failure mode of laying out SVG by arithmetic rather than by flow.
    for (let i = 0; i < boxes.length; i++) {
      for (let j = i + 1; j < boxes.length; j++) {
        const a = boxes[i].b, c = boxes[j].b;
        const ox = Math.min(a.right, c.right) - Math.max(a.left, c.left);
        const oy = Math.min(a.bottom, c.bottom) - Math.max(a.top, c.top);
        if (ox > 6 && oy > 6) {
          out.push({ kind: "COLLIDE", v: Math.round(oy), txt: `"${boxes[i].txt}" x "${boxes[j].txt}"`, size: 0 });
        }
      }
    }
    return out;
  }, { W, H, MARGIN, TOL });

  for (const r of rows) {
    if (r.kind === "SIZE") {
      if (r.v < smallest) { smallest = r.v; smallestWhere = `${f} — "${r.txt}"`; }
      continue;
    }
    bad++;
    console.log(`  ${r.kind} ${r.v}px · ${f} @${r.size}px · "${r.txt}"`);
  }
}
await browser.close();

console.log(`\nchecked ${files.length} posts · ${bad} overflow(s)`);
console.log(`smallest type: ${smallest}px (${smallestWhere})`);
if (bad) process.exit(1);
if (smallest < 23) { console.log("WARN: type below 23px is hard to read in the Instagram feed"); }
