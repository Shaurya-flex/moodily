/**
 * Page feedback: placement, the three signals, and what leaves the page.
 *
 * The block takes free text from a visitor and builds outbound URLs from it — a WhatsApp message and a
 * shared link — so the parts worth guarding are not cosmetic: that both carry the path and nothing from
 * the query string, that typed words never reach the dataLayer, and that transactional pages never ask.
 *
 * Local runs skip when Playwright is absent. CI must not skip — a guard that disappears with its
 * dependency is worse than no guard, so a missing import is a failure there.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

// one of each variant, plus pages that must never ask: mid-transaction, legal, and the two homepages
const ASKS = ["/services/google-business-profile/", "/guides/dukan-google-maps-par-kaise-laye/"];
const SILENT = ["/", "/international/", "/contact/", "/payment/success/", "/terms/", "/offers/founding-10/"];
// a page URL carrying things that must never be forwarded anywhere
const DIRTY = "?utm_source=instagram&order=ABC123#frag";

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

/** Capture what the share buttons hand to the OS sheet or to WhatsApp, instead of opening either. */
const STUB = () => {
  window.__shared = [];
  window.open = (url) => { window.__shared.push(url); return null; };
  // delete first: navigator.share is read-only where it exists
  try { delete navigator.share; } catch { /* absent already */ }
  Object.defineProperty(navigator, "share", {
    configurable: true,
    value: (d) => { window.__shared.push(JSON.stringify(d)); return Promise.resolve(); },
  });
};

let playwright = null;
try { ({ default: playwright } = await import("playwright")); } catch { /* reported below */ }

test("page feedback asks the right pages and leaks nothing", { concurrency: false }, async (t) => {
  if (!playwright) {
    assert.ok(!process.env.CI, "playwright is required in CI: run `npx playwright install --with-deps chromium`");
    t.skip("playwright not installed — run `npm i -D playwright` to enable the feedback guard locally");
    return;
  }
  const server = await serve();
  const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await playwright.chromium.launch();
  const context = await browser.newContext({ viewport: { width: 390, height: 900 } });
  // deterministic: no web fonts, no third-party anything
  await context.route("**/*", (r) => (r.request().url().startsWith(base) ? r.continue() : r.abort()));
  const page = await context.newPage();
  await page.addInitScript(STUB);

  try {
    for (const route of SILENT) {
      await page.goto(base + route, { waitUntil: "load" });
      assert.equal(await page.locator(".fb").count(), 0,
        `${route} must not ask for feedback — it is a homepage, legal page, or mid-transaction`);
    }

    for (const route of ASKS) {
      // A yes opens the rating and the share row, but never the box.
      await page.goto(base + route, { waitUntil: "load" });
      assert.equal(await page.locator(".fb").count(), 1, `${route} should ask for feedback`);
      assert.equal(await page.locator(".fb-step").isVisible(), false, "nothing is shown before answering");
      await page.locator('[data-fb-vote="up"]').click();
      await page.locator(".fb-step").waitFor({ state: "visible", timeout: 2000 });
      // `hidden` is a UA rule and .fb-row sets display:flex, so this silently stops working the
      // moment the author stylesheet gives the row a display of its own.
      assert.equal(await page.locator(".fb-row").isVisible(), false, "the buttons must go once answered");
      assert.equal(await page.locator(".fb-more").isVisible(), false, "a yes must not open the text box");
      assert.equal(await page.locator(".fb-thanks").isVisible(), true, "answering should acknowledge");
      assert.equal(await page.locator(".fb-bar").count(), 5, "the rating runs 1 to 5");

      const up = await page.evaluate(() => window.dataLayer.filter((d) => d.event === "page_feedback"));
      assert.equal(up.length, 1, "exactly one page_feedback event");
      assert.equal(up[0].label, "up");
      assert.equal(up[0].page_path, route, "the event must carry the route, or the owner cannot tell which page failed");

      // The rating fills up to the bar chosen, not just that one.
      await page.locator('label[for="fb-r4"]').click();
      const on = await page.evaluate(() =>
        [...document.querySelectorAll(".fb-bar")].map((b) => b.classList.contains("is-on")));
      assert.deepEqual(on, [true, true, true, true, false], "bars fill up to the chosen value");
      const rated = await page.evaluate(() => window.dataLayer.filter((d) => d.event === "page_rating"));
      assert.equal(rated.length, 1, "exactly one page_rating event");
      assert.equal(rated[0].label, "4");
      assert.equal(rated[0].page_path, route);
    }

    // A no, on a URL carrying a campaign tag, an order id and a fragment, with personal text typed in.
    const route = ASKS[0];
    const said = "मुझे 9876543210 पर call chahiye";
    await page.goto(base + route + DIRTY, { waitUntil: "load" });
    await page.locator('[data-fb-vote="down"]').click();
    await page.locator(".fb-text").waitFor({ state: "visible", timeout: 2000 });
    await page.locator(".fb-text").fill(said);
    await page.locator("[data-fb-send]").click();

    const href = await page.locator("[data-fb-send]").getAttribute("href");
    assert.match(href, /^https:\/\/wa\.me\/\d+\?text=/, "send must point at WhatsApp");
    const msg = new URL(href).searchParams.get("text");
    assert.ok(msg.includes(route), "the message must say which page it is about");
    assert.ok(msg.includes(said), "the message must carry what the visitor wrote");
    assert.ok(!msg.includes("order=") && !msg.includes("ABC123") && !msg.includes("frag"),
      "the message must carry the path only — a query or fragment can hold the visitor's own details");

    // Sharing: the pitch plus a link that says where it came from and nothing about who sent it.
    await page.locator("[data-fb-share]").click();
    await page.locator("[data-fb-copy]").click();
    const shared = await page.evaluate(() => window.__shared);
    assert.ok(shared.length >= 1, "share must hand something to the OS sheet or to WhatsApp");
    for (const out of shared) {
      assert.ok(out.includes("utm_source=share"), "a shared link should be attributable to a share");
      assert.ok(!out.includes("ABC123") && !out.includes("order=") && !out.includes("frag"),
        "a shared link must never carry the sharer's own query string or fragment");
      assert.ok(!out.includes(said) && !out.includes("9876543210"),
        "a shared link must never carry what the visitor typed into the feedback box");
    }

    // Nothing the visitor typed may reach analytics, and tracked links must be query-free.
    const events = await page.evaluate(() => window.dataLayer);
    const dump = JSON.stringify(events);
    assert.ok(!dump.includes("9876543210") && !dump.includes(said), "typed text must never reach the dataLayer");
    assert.ok(!dump.includes("ABC123"), "an order id in the page URL must never reach the dataLayer");
    const sent = events.filter((d) => d.event === "feedback_whatsapp");
    assert.equal(sent.length, 1, "exactly one feedback_whatsapp event");
    assert.ok(!String(sent[0].link_url || "").includes("?"), "the tracked link must be stripped of its query");
    assert.equal(events.filter((d) => d.event === "page_share").length, 2, "both share buttons report");
  } finally {
    await browser.close();
    server.close();
  }
});
