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

// ---------------------------------------------------------------- 50% deposit flow
const DEP_ENV = { ...ENV, RAZORPAY_WEBHOOK_SECRET: "unit_webhook_secret", PAYMENT_MODE: "test", RAZORPAY_KEY_ID: "rzp_test_unit" };
const depCatalog = {
  currency: "INR",
  deposits: {
    card: { name: "Digital Visiting Card", total_paise: 49900, deposit_paise: 25000, balance_paise: 24900 },
    broken: { name: "Broken", total_paise: 1000, deposit_paise: 600, balance_paise: 600 },
  },
};
const CUSTOMER = { name: "Asha Verma", phone: "+91 98765 43210", email: "asha@example.com" };
const ORDER_ID = "order_ABCDEFGHIJ1234";

function depFetch({ orderStatus = 200, order = null } = {}) {
  const calls = [];
  const impl = async (url, init = {}) => {
    calls.push({ url, init });
    if (url === ENV.CATALOG_URL) return Response.json(depCatalog);
    if (orderStatus !== 200) return new Response("{}", { status: orderStatus });
    if (init.method === "POST") {
      const b = JSON.parse(init.body);
      return Response.json({ id: ORDER_ID, amount: b.amount, currency: "INR", notes: b.notes, status: "created" });
    }
    return Response.json(order);
  };
  impl.calls = calls;
  return impl;
}
const get = (path) => new Request("https://pay.example" + path, { headers: { Origin: "https://moodily.in" } });

test("deposit create-order: 50% from catalogue, client amount ignored, MDLY id", async () => {
  const f = depFetch();
  const res = await worker.fetch(post("/api/payment/create-order", { service_id: "card", amount: 100, customer: CUSTOMER }), DEP_ENV, {}, f);
  const data = await res.json();
  assert.equal(res.status, 200);
  assert.equal(data.amount, 25000);
  assert.equal(data.total_paise, 49900);
  assert.equal(data.balance_paise, 24900);
  assert.match(data.moodily_order_id, /^MDLY-\d{8}-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{6}$/);
  assert.equal(data.prefill.contact, "919876543210");
  const sent = JSON.parse(f.calls.find((c) => c.url.includes("razorpay.com")).init.body);
  assert.equal(sent.amount, 25000);
  assert.equal(sent.receipt, data.moodily_order_id);
  assert.equal(sent.notes.kind, "deposit");
  assert.ok(!JSON.stringify(data).includes(DEP_ENV.RAZORPAY_KEY_SECRET));
});

test("deposit create-order rejects bad service, customer, catalogue and mode", async () => {
  const cases = [
    [{ service_id: "nope", customer: CUSTOMER }, DEP_ENV, 400],
    [{ service_id: "broken", customer: CUSTOMER }, DEP_ENV, 500],
    [{ service_id: "card" }, DEP_ENV, 400],
    [{ service_id: "card", customer: { ...CUSTOMER, name: "A" } }, DEP_ENV, 400],
    [{ service_id: "card", customer: { ...CUSTOMER, phone: "12345" } }, DEP_ENV, 400],
    [{ service_id: "card", customer: { ...CUSTOMER, email: "not-an-email" } }, DEP_ENV, 400],
    [{ service_id: "card", customer: CUSTOMER }, { ...DEP_ENV, PAYMENT_MODE: "live" }, 500],
  ];
  for (const [body, env, status] of cases) {
    const res = await worker.fetch(post("/api/payment/create-order", body), env, {}, depFetch());
    assert.equal(res.status, status, JSON.stringify(body));
  }
});

test("deposit verify: good signature returns summary without PII, bad fails", async () => {
  const notes = { moodily_order_id: "MDLY-20260918-ABCDEF", kind: "deposit", service_id: "card", service_name: "Digital Visiting Card", total_paise: "49900", deposit_paise: "25000", balance_paise: "24900", customer_name: "Asha", customer_phone: "919876543210", customer_email: "asha@example.com" };
  const f = depFetch({ order: { id: ORDER_ID, amount: 25000, status: "paid", notes } });
  const sig = createHmac("sha256", DEP_ENV.RAZORPAY_KEY_SECRET).update(`${ORDER_ID}|pay_1`).digest("hex");
  const ok = await worker.fetch(post("/api/payment/verify", { razorpay_order_id: ORDER_ID, razorpay_payment_id: "pay_1", razorpay_signature: sig }), DEP_ENV, {}, f);
  const data = await ok.json();
  assert.equal(ok.status, 200);
  assert.equal(data.verified, true);
  assert.equal(data.moodily_order_id, "MDLY-20260918-ABCDEF");
  assert.equal(data.balance_paise, 24900);
  assert.ok(!/asha|98765/i.test(JSON.stringify(data)));
  const bad = await worker.fetch(post("/api/payment/verify", { razorpay_order_id: ORDER_ID, razorpay_payment_id: "pay_1", razorpay_signature: "f".repeat(64) }), DEP_ENV, {}, f);
  assert.equal(bad.status, 400);
  assert.equal((await bad.json()).verified, false);
});

test("status: validates id, deposit orders only, no PII", async () => {
  const notes = { moodily_order_id: "MDLY-20260918-ABCDEF", kind: "deposit", service_id: "card", total_paise: "49900", deposit_paise: "25000", balance_paise: "24900", customer_name: "Asha", customer_email: "asha@example.com" };
  const paid = await worker.fetch(get(`/api/payment/status/${ORDER_ID}`), DEP_ENV, {}, depFetch({ order: { id: ORDER_ID, amount: 25000, status: "paid", notes } }));
  const data = await paid.json();
  assert.equal(paid.status, 200);
  assert.equal(data.paid, true);
  assert.ok(!/asha/i.test(JSON.stringify(data)));
  assert.equal(paid.headers.get("X-Robots-Tag"), "noindex");
  const pending = await (await worker.fetch(get(`/api/payment/status/${ORDER_ID}`), DEP_ENV, {}, depFetch({ order: { id: ORDER_ID, amount: 25000, status: "attempted", notes } }))).json();
  assert.equal(pending.paid, false);
  const offerOrder = await worker.fetch(get(`/api/payment/status/${ORDER_ID}`), DEP_ENV, {}, depFetch({ order: { id: ORDER_ID, status: "paid", notes: { offer_id: "founding-10" } } }));
  assert.equal(offerOrder.status, 404);
  const badId = await worker.fetch(get("/api/payment/status/..%2Fpayments"), DEP_ENV, {}, depFetch());
  assert.equal(badId.status, 400);
  const missing = await worker.fetch(get(`/api/payment/status/${ORDER_ID}`), DEP_ENV, {}, depFetch({ orderStatus: 400 }));
  assert.equal(missing.status, 404);
});

test("webhook: raw-body HMAC, retries idempotent, wrong/missing secret rejected", async () => {
  const raw = JSON.stringify({ event: "payment.captured", payload: { payment: { entity: { order_id: ORDER_ID, notes: { moodily_order_id: "MDLY-20260918-ABCDEF" } } } } });
  const sig = createHmac("sha256", DEP_ENV.RAZORPAY_WEBHOOK_SECRET).update(raw).digest("hex");
  const hook = (s, env = DEP_ENV) =>
    worker.fetch(new Request("https://pay.example/api/payment/webhook", { method: "POST", headers: { "X-Razorpay-Signature": s }, body: raw }), env, {}, depFetch());
  const first = await (await hook(sig)).json();
  const retry = await (await hook(sig)).json();
  assert.deepEqual(first, retry);
  assert.equal(first.moodily_order_id, "MDLY-20260918-ABCDEF");
  assert.equal((await hook("0".repeat(64))).status, 400);
  assert.equal((await hook(sig, { ...DEP_ENV, RAZORPAY_WEBHOOK_SECRET: "" })).status, 500);
  const withKeySecret = createHmac("sha256", DEP_ENV.RAZORPAY_KEY_SECRET).update(raw).digest("hex");
  assert.equal((await hook(withKeySecret)).status, 400);
});

test("health reports configuration without values", async () => {
  const res = await worker.fetch(get("/api/payment/health"), DEP_ENV, {}, depFetch());
  const data = await res.json();
  assert.equal(data.key_mode, "test");
  assert.equal(data.mode_matches_key, true);
  assert.equal(data.deposit_services, 2);
  assert.equal(data.webhook_secret_configured, true);
  const text = JSON.stringify(data);
  for (const v of [DEP_ENV.RAZORPAY_KEY_SECRET, DEP_ENV.RAZORPAY_WEBHOOK_SECRET, DEP_ENV.RAZORPAY_KEY_ID]) assert.ok(!text.includes(v));
  const mismatch = await (await worker.fetch(get("/api/payment/health"), { ...DEP_ENV, PAYMENT_MODE: "live" }, {}, depFetch())).json();
  assert.equal(mismatch.mode_matches_key, false);
});
