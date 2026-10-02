// Unit tests for the secure digital-delivery paths in worker/src/index.js.
// No network, no real keys, no real buckets.   node --test tests/delivery.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import worker, { resolveDigitalItem, serveDownload, ApiError } from "../worker/src/index.js";

/* in-memory fakes shaped like Cloudflare KV / R2 */
function kv() {
  const m = new Map();
  return { m, async get(k) { return m.has(k) ? m.get(k) : null; }, async put(k, v) { m.set(k, v); }, async delete(k) { m.delete(k); } };
}
function r2(files = {}) {
  return { async get(k) { return k in files ? { body: files[k], httpMetadata: { contentType: "application/pdf" } } : null; } };
}

const DIGITAL_URL = "https://moodily.in/digital.json";
const digitalCatalog = () => ({
  currency: "INR",
  products: {
    "ai-parents-india": {
      name: "AI for Parents & Senior Citizens — India",
      editions: {
        full: {
          licenses: {
            personal: { amount_paise: 9900, object_key: "ai-parents-india/v1.1/full-personal.pdf", label: "Full Guide — Personal", filename: "ai-parents-guide.pdf" },
            family: { amount_paise: 29900, object_key: "ai-parents-india/v1.1/family.zip", label: "Family Toolkit", filename: "family-toolkit.zip" },
          },
        },
        free: { licenses: { personal: { amount_paise: 0, object_key: "ai-parents-india/v1.1/free.pdf" } } }, // sampler: not purchasable here
      },
    },
  },
});

function mkEnv(files) {
  return {
    RAZORPAY_KEY_ID: "rzp_test_x", RAZORPAY_KEY_SECRET: "sekret", WEBHOOK_SECRET: "whsek",
    ALLOWED_ORIGINS: "https://moodily.in", DIGITAL_CATALOG_URL: DIGITAL_URL,
    ORDERS: kv(), TOKENS: kv(),
    PRODUCTS: r2(files ?? { "ai-parents-india/v1.1/full-personal.pdf": "%PDF-1.7 fake bytes", "ai-parents-india/v1.1/family.zip": "PK fake zip" }),
  };
}
function fakeFetch(orderId = "order_dg1") {
  return async (url, init) => {
    if (url === DIGITAL_URL) return Response.json(digitalCatalog());
    if (String(url).includes("razorpay.com")) return Response.json({ id: orderId, amount: JSON.parse(init.body).amount, currency: JSON.parse(init.body).currency });
    return new Response("{}", { status: 404 });
  };
}
const post = (path, body, origin = "https://moodily.in") =>
  new Request("https://pay.example" + path, { method: "POST", headers: { "Content-Type": "application/json", Origin: origin }, body: JSON.stringify(body) });
const sign = (orderId, paymentId, secret = "sekret") => createHmac("sha256", secret).update(`${orderId}|${paymentId}`).digest("hex");

test("resolveDigitalItem: amount + private key server-side; rejects bad ids and free tiers", () => {
  const cat = digitalCatalog();
  const it = resolveDigitalItem(cat, "ai-parents-india", "full", "personal");
  assert.equal(it.amount_paise, 9900);
  assert.equal(it.object_key, "ai-parents-india/v1.1/full-personal.pdf");
  for (const [p, e, l] of [["nope", "full", "personal"], ["ai-parents-india", "nope", "personal"], ["ai-parents-india", "full", "nope"], ["ai-parents-india", "free", "personal"]]) {
    assert.throws(() => resolveDigitalItem(cat, p, e, l), (err) => err instanceof ApiError);
  }
});

test("digital create-order: uses catalogue amount (not client), writes a PENDING record, leaks no secret", async () => {
  const env = mkEnv();
  const res = await worker.fetch(post("/api/create-order", { product_id: "ai-parents-india", edition: "full", license: "personal", amount: 1 }), env, {}, fakeFetch());
  const data = await res.json();
  assert.equal(res.status, 200);
  assert.equal(data.kind, "digital");
  assert.equal(data.amount, 9900);
  assert.equal(data.key_id, "rzp_test_x");
  assert.ok(!JSON.stringify(data).includes("sekret") && !JSON.stringify(data).includes("whsek"));
  const rec = JSON.parse(env.ORDERS.m.get("order_dg1"));
  assert.equal(rec.status, "created");
  assert.equal(rec.object_key, "ai-parents-india/v1.1/full-personal.pdf");
  assert.equal(rec.amount_paise, 9900);
});

test("verify-payment (digital): valid signature -> marks paid + mints a live token; failure mints nothing", async () => {
  const env = mkEnv();
  await worker.fetch(post("/api/create-order", { product_id: "ai-parents-india", edition: "full", license: "personal" }), env, {}, fakeFetch());

  // wrong signature: order stays 'created', no token
  const bad = await worker.fetch(post("/api/verify-payment", { razorpay_order_id: "order_dg1", razorpay_payment_id: "pay_1", razorpay_signature: "deadbeef" }), env, {}, fakeFetch());
  assert.equal(bad.status, 400);
  assert.equal((await bad.json()).verified, false);
  assert.equal(JSON.parse(env.ORDERS.m.get("order_dg1")).status, "created");
  assert.equal(env.TOKENS.m.size, 0);

  // correct signature: paid + token + download_url
  const ok = await worker.fetch(post("/api/verify-payment", { razorpay_order_id: "order_dg1", razorpay_payment_id: "pay_1", razorpay_signature: sign("order_dg1", "pay_1") }), env, {}, fakeFetch());
  const data = await ok.json();
  assert.equal(ok.status, 200);
  assert.equal(data.verified, true);
  assert.match(data.download_url, /^\/api\/download\?token=[0-9a-f]{64}$/);
  assert.ok(!JSON.stringify(data).includes("sekret"));
  assert.equal(JSON.parse(env.ORDERS.m.get("order_dg1")).status, "paid");
  assert.equal(env.TOKENS.m.get(data.download_token), "order_dg1");
});

test("download: streams the private file for a paid order, enforces the download cap", async () => {
  const env = mkEnv();
  await worker.fetch(post("/api/create-order", { product_id: "ai-parents-india", edition: "full", license: "personal" }), env, {}, fakeFetch());
  const v = await (await worker.fetch(post("/api/verify-payment", { razorpay_order_id: "order_dg1", razorpay_payment_id: "pay_1", razorpay_signature: sign("order_dg1", "pay_1") }), env, {}, fakeFetch())).json();
  const token = v.download_token;

  const dl = await worker.fetch(new Request(`https://pay.example/api/download?token=${token}`), env, {}, fakeFetch());
  assert.equal(dl.status, 200);
  assert.match(dl.headers.get("Content-Disposition"), /attachment; filename="ai-parents-guide\.pdf"/);
  assert.equal(dl.headers.get("Cache-Control"), "no-store, private");
  assert.equal(await dl.text(), "%PDF-1.7 fake bytes");
  assert.equal(JSON.parse(env.ORDERS.m.get("order_dg1")).downloads, 1);

  // exhaust the cap (already used 1) -> 429
  for (let i = 0; i < 4; i++) await worker.fetch(new Request(`https://pay.example/api/download?token=${token}`), env, {}, fakeFetch());
  const over = await worker.fetch(new Request(`https://pay.example/api/download?token=${token}`), env, {}, fakeFetch());
  assert.equal(over.status, 429);
});

test("download: invalid/expired token -> 410; unpaid order -> 403", async () => {
  const env = mkEnv();
  const gone = await worker.fetch(new Request("https://pay.example/api/download?token=nope"), env, {}, fakeFetch());
  assert.equal(gone.status, 410);

  // create (but do NOT pay) an order, then point a token at it -> 403
  await worker.fetch(post("/api/create-order", { product_id: "ai-parents-india", edition: "full", license: "personal" }), env, {}, fakeFetch());
  await env.TOKENS.put("manualtoken", "order_dg1");
  const unpaid = await worker.fetch(new Request("https://pay.example/api/download?token=manualtoken"), env, {}, fakeFetch());
  assert.equal(unpaid.status, 403);
});

test("webhook: valid signature marks the order paid, idempotently; bad signature -> 400", async () => {
  const env = mkEnv();
  await worker.fetch(post("/api/create-order", { product_id: "ai-parents-india", edition: "full", license: "personal" }), env, {}, fakeFetch());
  const raw = JSON.stringify({ event: "payment.captured", payload: { payment: { entity: { id: "pay_wh", order_id: "order_dg1" } } } });

  const bad = new Request("https://pay.example/api/webhook", { method: "POST", headers: { "Content-Type": "application/json", "X-Razorpay-Signature": "wrong" }, body: raw });
  assert.equal((await worker.fetch(bad, env, {}, fakeFetch())).status, 400);
  assert.equal(JSON.parse(env.ORDERS.m.get("order_dg1")).status, "created");

  const good = () => new Request("https://pay.example/api/webhook", { method: "POST", headers: { "Content-Type": "application/json", "X-Razorpay-Signature": createHmac("sha256", "whsek").update(raw).digest("hex") }, body: raw });
  const r1 = await worker.fetch(good(), env, {}, fakeFetch());
  assert.equal(r1.status, 200);
  const afterFirst = JSON.parse(env.ORDERS.m.get("order_dg1"));
  assert.equal(afterFirst.status, "paid");
  assert.equal(afterFirst.payment_id, "pay_wh");
  const paidAt = afterFirst.paid_at;
  // retry the same event: still one paid order, paid_at unchanged (no duplicate entitlement)
  const r2res = await worker.fetch(good(), env, {}, fakeFetch());
  assert.equal(r2res.status, 200);
  assert.equal(JSON.parse(env.ORDERS.m.get("order_dg1")).paid_at, paidAt);
});

test("verify-payment for a SERVICE order (not in ORDERS) is unchanged — no token minted", async () => {
  const env = mkEnv();
  const res = await worker.fetch(post("/api/verify-payment", { razorpay_order_id: "order_service", razorpay_payment_id: "pay_s", razorpay_signature: sign("order_service", "pay_s") }), env, {}, fakeFetch());
  const data = await res.json();
  assert.equal(data.verified, true);
  assert.equal(data.download_token, undefined);
});

test("serveDownload throws 404 cleanly when delivery bindings are absent", async () => {
  await assert.rejects(() => serveDownload("t", { TOKENS: null }), (e) => e instanceof ApiError && e.status === 404);
});
