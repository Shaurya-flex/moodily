// Unit tests for worker/src/index.js (no network, no real keys).  node --test tests/worker.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import worker from "../worker/src/index.js";

const ENV = { RAZORPAY_KEY_ID: "rzp_test_unit", RAZORPAY_KEY_SECRET: "unit_test_secret", ALLOWED_ORIGINS: "https://moodily.in", CATALOG_URL: "https://moodily.in/catalog.json" };
const future = new Date(Date.now() + 2 * 864e5).toISOString();
const catalog = (offer = {}) => ({
  currency: "INR",
  offer: { id: "founding-10", active: true, ends_at: future, slots_left: 5, ...offer },
  items: { svc: { name: "Founding 10 — Svc", amount_paise: 149900 }, tiny: { name: "Tiny", amount_paise: 50 } },
});
const post = (path, body, origin = "https://moodily.in") =>
  new Request("https://pay.example" + path, { method: "POST", headers: { "Content-Type": "application/json", Origin: origin }, body: JSON.stringify(body) });

function fakeFetch({ cat = catalog(), orderStatus = 200 } = {}) {
  const calls = [];
  const impl = async (url, init) => {
    calls.push({ url, init });
    if (url === ENV.CATALOG_URL) return Response.json(cat);
    if (orderStatus !== 200) return new Response("{}", { status: orderStatus });
    return Response.json({ id: "order_123", amount: JSON.parse(init.body).amount, currency: "INR" });
  };
  impl.calls = calls;
  return impl;
}

test("create-order uses catalogue amount, not the client", async () => {
  const f = fakeFetch();
  const res = await worker.fetch(post("/api/create-order", { service_id: "svc", amount: 100 }), ENV, {}, f);
  const data = await res.json();
  assert.equal(res.status, 200);
  assert.equal(data.order_id, "order_123");
  assert.equal(data.amount, 149900);
  assert.equal(data.key_id, "rzp_test_unit");
  assert.ok(!JSON.stringify(data).includes(ENV.RAZORPAY_KEY_SECRET));
  assert.equal(res.headers.get("Access-Control-Allow-Origin"), "https://moodily.in");
  const orderCall = f.calls.find((c) => c.url.includes("razorpay.com"));
  assert.match(orderCall.init.headers.Authorization, /^Basic /);
});

test("create-order validations and error mapping", async () => {
  const cases = [
    [{ service_id: "nope" }, {}, 400],
    [{ service_id: "tiny" }, {}, 400],
    [{ service_id: "svc" }, { cat: catalog({ slots_left: 0 }) }, 409],
    [{ service_id: "svc" }, { cat: catalog({ ends_at: new Date(Date.now() - 1000).toISOString() }) }, 409],
    [{ service_id: "svc" }, { orderStatus: 401 }, 401],
    [{ service_id: "svc" }, { orderStatus: 500 }, 500],
  ];
  for (const [body, opts, status] of cases) {
    const res = await worker.fetch(post("/api/create-order", body), ENV, {}, fakeFetch(opts));
    assert.equal(res.status, status, JSON.stringify({ body, opts }));
  }
});

test("verify-payment accepts only a valid HMAC-SHA256 signature", async () => {
  const sig = createHmac("sha256", ENV.RAZORPAY_KEY_SECRET).update("order_1|pay_1").digest("hex");
  const ok = await worker.fetch(post("/api/verify-payment", { razorpay_order_id: "order_1", razorpay_payment_id: "pay_1", razorpay_signature: sig }), ENV, {}, fakeFetch());
  assert.equal(ok.status, 200);
  assert.equal((await ok.json()).verified, true);

  const bad = await worker.fetch(post("/api/verify-payment", { razorpay_order_id: "order_1", razorpay_payment_id: "pay_1", razorpay_signature: "0".repeat(64) }), ENV, {}, fakeFetch());
  assert.equal(bad.status, 400);
  assert.equal((await bad.json()).verified, false);

  const missing = await worker.fetch(post("/api/verify-payment", { razorpay_order_id: "order_1" }), ENV, {}, fakeFetch());
  assert.equal(missing.status, 400);
});

test("CORS preflight, unknown origin and unconfigured secrets", async () => {
  const pre = await worker.fetch(new Request("https://pay.example/api/create-order", { method: "OPTIONS", headers: { Origin: "https://moodily.in" } }), ENV, {}, fakeFetch());
  assert.equal(pre.status, 204);
  const evil = await worker.fetch(post("/api/create-order", { service_id: "svc" }, "https://evil.example"), ENV, {}, fakeFetch());
  assert.equal(evil.headers.get("Access-Control-Allow-Origin"), null);
  const noKeys = await worker.fetch(post("/api/create-order", { service_id: "svc" }), { ...ENV, RAZORPAY_KEY_SECRET: "" }, {}, fakeFetch());
  assert.equal(noKeys.status, 500);
});
