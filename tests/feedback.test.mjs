/**
 * Page feedback: placement, the two answers, and what reaches WhatsApp and analytics.
 *
 * The widget takes free text from a visitor and builds an outbound URL from it, so the parts worth
 * guarding are not cosmetic: that the message carries the path and nothing from the query string,
 * that the typed words never reach the dataLayer, and that transactional pages never ask at all.
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

  try {
    for (const route of SILENT) {
      await page.goto(base + route, { waitUntil: "load" });
      assert.equal(await page.locator(".fb").count(), 0,
        `${route} must not ask for feedback — it is a homepage, legal page, or mid-transaction`);
    }

    for (const route of ASKS) {
      // "Yes" ends the exchange: thanks, and no box to fill in.
      await page.goto(base + route, { waitUntil: "load" });
      assert.equal(await page.locator(".fb").count(), 1, `${route} should ask for feedback`);
      await page.locator('[data-fb-vote="up"]').click();
      await assert.doesNotReject(page.locator(".fb-thanks").waitFor({ state: "visible", timeout: 2000 }));
      assert.equal(await page.locator(".fb-more").isVisible(), false, "a yes must not open the text box");
      // `hidden` is a UA rule and .fb-row sets display:flex, so this silently stops working
      // the moment the author stylesheet gives the row a display of its own.
      assert.equal(await page.locator(".fb-row").isVisible(), false, "the buttons must go once answered");
      const up = await page.evaluate(() => window.dataLayer.filter((d) => d.event === "page_feedback"));
      assert.equal(up.length, 1, "exactly one page_feedback event");
      assert.equal(up[0].label, "up");
      assert.equal(up[0].page_path, route, "the event must carry the route, or the owner cannot tell which page failed");
    }

    // "No", with a query string on the URL and personal-looking text typed in.
    const route = ASKS[0];
    const said = "मुझे 9876543210 पर call chahiye";
    await page.goto(base + route + "?utm_source=instagram&order=ABC123", { waitUntil: "load" });
    await page.locator('[data-fb-vote="down"]').click();
    await page.locator(".fb-text").waitFor({ state: "visible", timeout: 2000 });
    await page.locator(".fb-text").fill(said);
    await page.locator("[data-fb-send]").click();

    const href = await page.locator("[data-fb-send]").getAttribute("href");
    assert.match(href, /^https:\/\/wa\.me\/\d+\?text=/, "send must point at WhatsApp");
    const msg = decodeURIComponent(new URL(href).searchParams.get("text"));
    assert.ok(msg.includes(route), "the message must say which page it is about");
    assert.ok(msg.includes(said), "the message must carry what the visitor wrote");
    assert.ok(!msg.includes("utm_source") && !msg.includes("ABC123"),
      "the message must carry the path only — a query string can hold the visitor's own details");

    // Nothing the visitor typed may reach analytics, and the tracked link must be query-free.
    const events = await page.evaluate(() => window.dataLayer);
    const dump = JSON.stringify(events);
    assert.ok(!dump.includes("9876543210") && !dump.includes(said), "typed text must never reach the dataLayer");
    assert.ok(!dump.includes("ABC123"), "an order id in the page URL must never reach the dataLayer");
    const sent = events.filter((d) => d.event === "feedback_whatsapp");
    assert.equal(sent.length, 1, "exactly one feedback_whatsapp event");
    assert.ok(!String(sent[0].link_url || "").includes("?"), "the tracked link must be stripped of its query");
    assert.equal(await page.locator(".fb-thanks").isVisible(), true, "sending should acknowledge");
  } finally {
    await browser.close();
    server.close();
  }
});
