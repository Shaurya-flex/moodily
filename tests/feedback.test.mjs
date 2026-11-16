/**
 * The floating feedback widget, and the WhatsApp sheet's payment mode.
 *
 * Both take free text from a visitor and build outbound URLs from it, so what is guarded here is
 * not cosmetic: that the WhatsApp message and the shared link carry the path and nothing from the
 * query string, that typed words never reach the dataLayer, that a drag never opens the panel by
 * accident, that the panel cannot hang off the screen, and that someone who has already paid is
 * asked for a Payment ID rather than their name, business and city all over again.
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

const SERVICE = "/services/google-business-profile/";
const GUIDE = "/guides/dukan-google-maps-par-kaise-laye/";
// the widget is on every real page now, including the ones that used to be skipped
const EVERYWHERE = ["/", "/international/", "/contact/", "/terms/", "/payment/received/", GUIDE, SERVICE];
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
  try { delete navigator.share; } catch { /* absent already */ }
  Object.defineProperty(navigator, "share", {
    configurable: true,
    value: (d) => { window.__shared.push(JSON.stringify(d)); return Promise.resolve(); },
  });
};

let playwright = null;
try { ({ default: playwright } = await import("playwright")); } catch { /* reported below */ }

async function withPage(fn) {
  const server = await serve();
  const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await playwright.chromium.launch();
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  // deterministic: no web fonts, no third-party anything
  await context.route("**/*", (r) => (r.request().url().startsWith(base) ? r.continue() : r.abort()));
  await context.addInitScript(STUB);
  const page = await context.newPage();
  try { await fn(page, base); } finally { await browser.close(); server.close(); }
}

test("feedback widget: everywhere, movable, and leaks nothing", { concurrency: false }, async (t) => {
  if (!playwright) {
    assert.ok(!process.env.CI, "playwright is required in CI: run `npx playwright install --with-deps chromium`");
    t.skip("playwright not installed — run `npm i -D playwright` to enable the feedback guard locally");
    return;
  }
  await withPage(async (page, base) => {
    for (const route of EVERYWHERE) {
      await page.goto(base + route, { waitUntil: "load" });
      assert.equal(await page.locator("#fbwTab").isVisible(), true, `${route} should offer feedback`);
      assert.equal(await page.locator("#fbwPanel").isVisible(), false, `${route} must not open it unasked`);
    }

    // A yes opens the rating and the share row, but never the text box.
    await page.goto(base + SERVICE, { waitUntil: "load" });
    await page.locator("#fbwTab").click();
    await page.locator("#fbwPanel").waitFor({ state: "visible", timeout: 2000 });
    await page.locator('[data-fb-vote="up"]').click();
    assert.equal(await page.locator(".fb-row").isVisible(), false, "the buttons must go once answered");
    assert.equal(await page.locator(".fb-more").isVisible(), false, "a yes must not open the text box");
    assert.equal(await page.locator(".fb-thanks").isVisible(), true, "answering should acknowledge");
    assert.equal(await page.locator(".fb-bar").count(), 5, "the rating runs 1 to 5");
    const up = await page.evaluate(() => window.dataLayer.filter((d) => d.event === "page_feedback"));
    assert.equal(up.length, 1);
    assert.equal(up[0].label, "up");
    assert.equal(up[0].page_path, SERVICE, "the event must carry the route, or the owner cannot tell which page failed");

    // The rating fills up to the chosen bar, not just that one.
    await page.locator('label[for="fb-r4"]').click();
    assert.deepEqual(
      await page.evaluate(() => [...document.querySelectorAll(".fb-bar")].map((b) => b.classList.contains("is-on"))),
      [true, true, true, true, false], "bars fill up to the chosen value");
    const rated = await page.evaluate(() => window.dataLayer.filter((d) => d.event === "page_rating"));
    assert.equal(rated.length, 1);
    assert.equal(rated[0].label, "4");

    // Dragging moves it to the other edge, is remembered, and must NOT open the panel on drop.
    await page.locator("#fbwClose").click();
    const tab = await page.locator("#fbwTab").boundingBox();
    await page.mouse.move(tab.x + 20, tab.y + 26);
    await page.mouse.down();
    await page.mouse.move(60, 300, { steps: 12 });
    await page.mouse.up();
    assert.equal(await page.locator("#fbw").getAttribute("data-side"), "left", "it should snap to the near edge");
    assert.equal(await page.locator("#fbwPanel").isVisible(), false,
      "the click a browser fires after a drag must not count as a tap");
    const pos = JSON.parse(await page.evaluate(() => localStorage.getItem("moodily_fbw")));
    assert.equal(pos.side, "left", "where it was put must be remembered");

    // However far it is dragged, the panel still has to open inside the screen.
    await page.mouse.move(60, 300);
    await page.mouse.down();
    await page.mouse.move(60, 835, { steps: 10 });   // drag it to the very bottom
    await page.mouse.up();
    await page.locator("#fbwTab").click();
    await page.locator("#fbwPanel").waitFor({ state: "visible", timeout: 2000 });
    const box = await page.locator("#fbwPanel").boundingBox();
    assert.ok(box.y >= 0 && box.y + box.height <= 844 && box.x >= 0 && box.x + box.width <= 390,
      `panel must stay on screen, got ${JSON.stringify(box)}`);
  });
});

test("feedback widget: what reaches WhatsApp, the share sheet and analytics", { concurrency: false }, async (t) => {
  if (!playwright) { t.skip("playwright not installed"); return; }
  await withPage(async (page, base) => {
    const said = "मुझे 9876543210 पर call chahiye";
    await page.goto(base + SERVICE + DIRTY, { waitUntil: "load" });
    await page.locator("#fbwTab").click();
    await page.locator('[data-fb-vote="down"]').click();
    await page.locator(".fb-text").waitFor({ state: "visible", timeout: 2000 });
    await page.locator(".fb-text").fill(said);
    await page.locator("[data-fb-send]").click();

    const href = await page.locator("[data-fb-send]").getAttribute("href");
    assert.match(href, /^https:\/\/wa\.me\/\d+\?text=/, "send must point at WhatsApp");
    const msg = new URL(href).searchParams.get("text");
    assert.ok(msg.includes(SERVICE), "the message must say which page it is about");
    assert.ok(msg.includes(said), "the message must carry what the visitor wrote");
    assert.ok(!msg.includes("order=") && !msg.includes("ABC123") && !msg.includes("frag"),
      "the message must carry the path only — a query or fragment can hold the visitor's own details");

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

    const events = await page.evaluate(() => window.dataLayer);
    const dump = JSON.stringify(events);
    assert.ok(!dump.includes("9876543210") && !dump.includes(said), "typed text must never reach the dataLayer");
    assert.ok(!dump.includes("ABC123"), "an order id in the page URL must never reach the dataLayer");
    assert.equal(events.filter((d) => d.event === "page_share").length, 2, "both share buttons report");
    const sent = events.filter((d) => d.event === "feedback_whatsapp");
    assert.equal(sent.length, 1);
    assert.ok(!String(sent[0].link_url || "").includes("?"), "the tracked link must be stripped of its query");
  });
});

test("after paying, the sheet asks for a Payment ID and nothing else", { concurrency: false }, async (t) => {
  if (!playwright) { t.skip("playwright not installed"); return; }
  await withPage(async (page, base) => {
    await page.goto(base + "/payment/received/", { waitUntil: "load" });
    // Assert the mode before clicking it. Without this the regression shows up as a 30-second
    // locator timeout with nothing in the message about what was actually lost.
    assert.equal(await page.locator("a[data-wa-form]").first().getAttribute("data-wa-form"), "payment",
      "the post-payment WhatsApp button must open the sheet in payment mode, not the full enquiry");
    await page.locator('a[data-wa-form="payment"]').click();
    await page.locator("#wrSheet").waitFor({ state: "visible", timeout: 2000 });

    assert.equal(await page.locator("#wrEnquiry").isVisible(), false,
      "a customer who has already paid must not be asked for name, business and city again");
    assert.equal(await page.locator("#wrPayField").isVisible(), true, "they must be asked for the Payment ID");

    await page.locator("#wrSend").click();
    assert.equal(await page.locator("#wrError").isVisible(), true, "an empty Payment ID must be refused");

    await page.locator("#wrPayId").fill("pay_RabcDEF1234567");
    await page.locator("#wrSend").click();
    const url = await page.evaluate(() => window.__shared[0]);
    const msg = decodeURIComponent(url.split("?text=")[1]);
    assert.ok(msg.includes("pay_RabcDEF1234567"), "the Payment ID must reach WhatsApp");
    assert.ok(msg.includes("/payment/received/"), "the message should say where it came from");
    assert.ok(!/Business:|City:|Service:/.test(msg), "no empty enquiry fields may ride along");
    assert.equal(
      (await page.evaluate(() => window.dataLayer.filter((d) => d.event === "wa_payment_id_sent"))).length, 1);

    // The enquiry sheet elsewhere must be untouched by any of this.
    await page.goto(base + SERVICE, { waitUntil: "load" });
    await page.locator('a[data-wa-form="1"]').first().click();
    await page.locator("#wrSheet").waitFor({ state: "visible", timeout: 2000 });
    assert.equal(await page.locator("#wrEnquiry").isVisible(), true, "a service page still asks for the details");
    assert.equal(await page.locator("#wrPayField").isVisible(), false, "and must not ask for a Payment ID");
  });
});
