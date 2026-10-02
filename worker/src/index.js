/**
 * Moodily payments API — Cloudflare Worker for Razorpay Standard Checkout + secure digital delivery.
 *
 * SERVICES (unchanged, backward compatible):
 *   POST /api/create-order   { service_id }  -> { order_id, amount, currency, key_id, name, description }
 *   POST /api/verify-payment { razorpay_order_id, razorpay_payment_id, razorpay_signature } -> { verified, order_id, payment_id }
 *
 * DIGITAL PRODUCTS (store — AI-with-Saurabh guide, etc.):
 *   POST /api/create-order   { product_id, edition, license } -> { order_id, amount, currency, key_id, name, description, kind:"digital" }
 *                            ...and writes a PENDING order record to env.ORDERS (KV/D1-shaped).
 *   POST /api/verify-payment { razorpay_order_id, razorpay_payment_id, razorpay_signature }
 *                            ...if the order is digital and paid: marks it paid, mints a short-lived
 *                               download token, and returns { verified, order_id, payment_id, download_token, download_url }.
 *   POST /api/webhook        Razorpay server-to-server confirmation (authoritative). Idempotent.
 *   GET  /api/download?token=... -> streams the private file from R2 ONLY for a paid order with a live token.
 *
 * SECURITY:
 *   - RAZORPAY_KEY_SECRET and WEBHOOK_SECRET stay server-side. Never returned to the browser. Tests assert this.
 *   - Amounts are NEVER taken from the browser: services from CATALOG_URL, digital from DIGITAL_CATALOG_URL.
 *   - The paid PDF is never at a permanent public URL: it lives in a PRIVATE R2 bucket and is only ever
 *     streamed through /api/download after token + paid-status validation.
 *   - Bindings (owner provisions these — see wrangler.toml): env.ORDERS (KV), env.TOKENS (KV, native TTL),
 *     env.PRODUCTS (R2, private bucket of paid files). All logic is in pure functions that take these as
 *     arguments, so unit tests inject in-memory fakes (no network, no real keys, no real buckets).
 */
const ORDERS_URL = "https://api.razorpay.com/v1/orders";
const MIN_AMOUNT_PAISE = 100;
const TOKEN_TTL_SECONDS = 60 * 60;   // download token lives 1 hour after payment verification
const MAX_DOWNLOADS = 5;             // entitlement: a paid order may be downloaded at most this many times
const ORDER_RECORD_TTL_SECONDS = 60 * 60 * 24 * 400; // keep order records ~13 months (support / re-issue window)

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

/* ----------------------------- shared crypto ------------------------------ */

export async function hmacHex(secret, message) {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = await crypto.subtle.sign("HMAC", key, enc.encode(message));
  return [...new Uint8Array(mac)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// Back-compat: existing name used by tests for the checkout signature.
export async function signatureFor(orderId, paymentId, secret) {
  return hmacHex(secret, `${orderId}|${paymentId}`);
}

function safeEqual(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

// 256-bit unguessable, URL-safe token.
function newToken() {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/* ------------------------------- services --------------------------------- */

export function resolveItem(catalog, serviceId, now = Date.now()) {
  const item = (catalog.items || {})[serviceId];
  if (!item) throw new ApiError(400, "Unknown service");
  const offer = catalog.offer || {};
  if (!offer.active || !(offer.slots_left > 0) || now > Date.parse(offer.ends_at)) {
    throw new ApiError(409, "यह offer समाप्त हो गया है।");
  }
  if (!Number.isInteger(item.amount_paise) || item.amount_paise < MIN_AMOUNT_PAISE) {
    throw new ApiError(400, "Amount must be at least 100 paise");
  }
  return { item, offer };
}

export async function createOrder(serviceId, env, catalog, fetchImpl = fetch) {
  const { item, offer } = resolveItem(catalog, serviceId);
  const order = await razorpayCreateOrder(
    { amount: item.amount_paise, currency: catalog.currency || "INR", receipt: `${offer.id}-${Date.now().toString(16)}`.slice(0, 40), notes: { service_id: serviceId, offer_id: offer.id } },
    env,
    fetchImpl,
  );
  return { order_id: order.id, amount: order.amount, currency: order.currency, key_id: env.RAZORPAY_KEY_ID, name: "Moodily", description: item.name };
}

/* --------------------------- digital products ----------------------------- */

// Resolve amount + private object key SERVER-SIDE from (product_id, edition, license).
// The browser only ever sends the three identifiers — never a price and never a file path.
export function resolveDigitalItem(catalog, productId, edition, license) {
  const product = (catalog.products || {})[productId];
  if (!product) throw new ApiError(400, "Unknown product");
  const ed = (product.editions || {})[edition];
  if (!ed) throw new ApiError(400, "Unknown edition");
  const item = (ed.licenses || ed)[license]; // licenses may be nested or flat per edition
  if (!item || typeof item !== "object") throw new ApiError(400, "Unknown licence");
  if (!Number.isInteger(item.amount_paise) || item.amount_paise < MIN_AMOUNT_PAISE) {
    throw new ApiError(400, "This product is not purchasable here"); // e.g. free tiers / waitlist
  }
  if (!item.object_key || typeof item.object_key !== "string") throw new ApiError(500, "Product file not configured");
  return {
    name: item.label || product.name || productId,
    amount_paise: item.amount_paise,
    currency: item.currency || product.currency || catalog.currency || "INR",
    object_key: item.object_key,
    filename: item.filename || `${productId}-${edition}-${license}.pdf`,
  };
}

async function razorpayCreateOrder(payload, env, fetchImpl) {
  let res;
  try {
    res = await fetchImpl(ORDERS_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Basic " + btoa(`${env.RAZORPAY_KEY_ID}:${env.RAZORPAY_KEY_SECRET}`) },
      body: JSON.stringify(payload),
    });
  } catch {
    throw new ApiError(500, "Could not create order");
  }
  if (res.status === 401) throw new ApiError(401, "Payment gateway authentication failed");
  if (!res.ok) throw new ApiError(500, "Could not create order");
  return res.json();
}

export async function createDigitalOrder(params, env, catalog, fetchImpl = fetch, now = Date.now()) {
  if (!env.ORDERS) throw new ApiError(500, "Delivery store not configured");
  const productId = String(params.product_id || "");
  const edition = String(params.edition || "");
  const license = String(params.license || "");
  const item = resolveDigitalItem(catalog, productId, edition, license);
  const order = await razorpayCreateOrder(
    {
      amount: item.amount_paise,
      currency: item.currency,
      receipt: `dg-${Date.now().toString(16)}`.slice(0, 40),
      notes: { kind: "digital", product_id: productId, edition, license },
    },
    env,
    fetchImpl,
  );
  // Durable order record. No PII collected here — only what's needed to deliver the file.
  const record = {
    order_id: order.id,
    kind: "digital",
    product_id: productId,
    edition,
    license,
    object_key: item.object_key,
    filename: item.filename,
    name: item.name,
    amount_paise: order.amount,
    currency: order.currency,
    status: "created",
    payment_id: null,
    downloads: 0,
    created_at: now,
    paid_at: null,
  };
  await env.ORDERS.put(order.id, JSON.stringify(record), { expirationTtl: ORDER_RECORD_TTL_SECONDS });
  return { order_id: order.id, amount: order.amount, currency: order.currency, key_id: env.RAZORPAY_KEY_ID, name: "Moodily", description: item.name, kind: "digital" };
}

// Mark a digital order paid and mint a short-lived download token. Idempotent: safe to call from
// BOTH verify-payment (browser return) and the webhook (server-to-server), and safe to call twice.
export async function finalizeDigitalOrder(orderId, paymentId, env, now = Date.now()) {
  if (!env.ORDERS) return null;
  const raw = await env.ORDERS.get(orderId);
  if (!raw) return null; // not a digital order (e.g. a service order) — nothing to do
  const record = JSON.parse(raw);
  if (record.status !== "paid") {
    record.status = "paid";
    record.payment_id = paymentId || record.payment_id || null;
    record.paid_at = record.paid_at || now;
    await env.ORDERS.put(orderId, JSON.stringify(record), { expirationTtl: ORDER_RECORD_TTL_SECONDS });
  }
  const token = newToken();
  if (env.TOKENS) await env.TOKENS.put(token, orderId, { expirationTtl: TOKEN_TTL_SECONDS });
  return { order_id: orderId, download_token: token };
}

export async function verifyPayment(body, env) {
  const { razorpay_order_id: orderId, razorpay_payment_id: paymentId, razorpay_signature: signature } = body || {};
  if (![orderId, paymentId, signature].every((v) => typeof v === "string" && v)) {
    throw new ApiError(400, "Missing payment fields");
  }
  const expected = await hmacHex(env.RAZORPAY_KEY_SECRET, `${orderId}|${paymentId}`);
  if (!safeEqual(expected, signature)) throw new ApiError(400, "Payment signature verification failed");
  const base = { verified: true, order_id: orderId, payment_id: paymentId };
  // If this is a digital order, finalize + mint a token so the success page can fetch the file.
  const fin = await finalizeDigitalOrder(orderId, paymentId, env);
  if (fin) return { ...base, download_token: fin.download_token, download_url: `/api/download?token=${fin.download_token}` };
  return base; // service order — unchanged contract
}

// Razorpay webhook. Authoritative + idempotent. Signature = HMAC-SHA256(rawBody, WEBHOOK_SECRET).
export async function handleWebhook(rawBody, signature, env, now = Date.now()) {
  if (!env.WEBHOOK_SECRET) throw new ApiError(500, "Webhook not configured");
  const expected = await hmacHex(env.WEBHOOK_SECRET, rawBody);
  if (!safeEqual(expected, signature || "")) throw new ApiError(400, "Invalid webhook signature");
  let event;
  try {
    event = JSON.parse(rawBody);
  } catch {
    throw new ApiError(400, "Invalid JSON");
  }
  const p = event.payload || {};
  const orderId = p.payment?.entity?.order_id || p.order?.entity?.id || null;
  const paymentId = p.payment?.entity?.id || null;
  // Only 'paid'/'captured' style events entitle delivery. Anything else is acknowledged and ignored.
  const paidEvent = event.event === "payment.captured" || event.event === "order.paid";
  if (paidEvent && orderId) await finalizeDigitalOrder(orderId, paymentId, env, now); // no-op if already paid or not a digital order
  return { received: true }; // always 200 so Razorpay stops retrying
}

// Gate + stream the private file. Never a public URL: reachable only with a live token for a paid order.
export async function serveDownload(token, env, now = Date.now()) {
  if (!token || !env.TOKENS || !env.ORDERS || !env.PRODUCTS) throw new ApiError(404, "Not found");
  const orderId = await env.TOKENS.get(token);
  if (!orderId) throw new ApiError(410, "This download link has expired. Please re-open your confirmation email or contact support.");
  const raw = await env.ORDERS.get(orderId);
  if (!raw) throw new ApiError(404, "Order not found");
  const record = JSON.parse(raw);
  if (record.status !== "paid") throw new ApiError(403, "Payment not confirmed");
  if ((record.downloads || 0) >= MAX_DOWNLOADS) throw new ApiError(429, "Download limit reached for this order. Contact support if you need access.");
  const obj = await env.PRODUCTS.get(record.object_key);
  if (!obj) throw new ApiError(404, "File not available");
  record.downloads = (record.downloads || 0) + 1;
  record.last_download_at = now;
  await env.ORDERS.put(orderId, JSON.stringify(record), { expirationTtl: ORDER_RECORD_TTL_SECONDS });
  const headers = {
    "Content-Type": obj.httpMetadata?.contentType || "application/pdf",
    "Content-Disposition": `attachment; filename="${record.filename || "moodily-download.pdf"}"`,
    "Cache-Control": "no-store, private",
    "X-Content-Type-Options": "nosniff",
  };
  return new Response(obj.body, { status: 200, headers });
}

/* -------------------------------- catalog --------------------------------- */

async function loadCatalog(url, fetchImpl) {
  const res = await fetchImpl(url, { cf: { cacheTtl: 60 } });
  if (!res.ok) throw new ApiError(500, "Price catalogue unavailable");
  return res.json();
}

/* -------------------------------- router ---------------------------------- */

export default {
  async fetch(request, env, _ctx, fetchImpl = fetch) {
    const origin = request.headers.get("Origin") || "";
    const allowed = (env.ALLOWED_ORIGINS || "").split(",").map((s) => s.trim()).filter(Boolean);
    const cors = allowed.includes(origin)
      ? { "Access-Control-Allow-Origin": origin, "Access-Control-Allow-Methods": "GET, POST, OPTIONS", "Access-Control-Allow-Headers": "Content-Type", Vary: "Origin" }
      : {};
    const json = (status, data) => new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json", ...cors } });
    const { pathname, searchParams } = new URL(request.url);

    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });

    try {
      // Gated download — a browser GET navigation (no CORS needed). Kept before the POST-only guard.
      if (pathname === "/api/download") {
        if (request.method !== "GET") throw new ApiError(405, "Method not allowed");
        return await serveDownload(searchParams.get("token") || "", env);
      }

      if (request.method !== "POST") throw new ApiError(405, "Method not allowed");
      if (!env.RAZORPAY_KEY_ID || !env.RAZORPAY_KEY_SECRET) throw new ApiError(500, "Payment server not configured");

      // Webhook needs the RAW body for signature verification — read it before any JSON.parse.
      if (pathname === "/api/webhook") {
        const rawBody = await request.text();
        const sig = request.headers.get("X-Razorpay-Signature") || request.headers.get("x-razorpay-signature") || "";
        return json(200, await handleWebhook(rawBody, sig, env));
      }

      let body;
      try {
        body = await request.json();
      } catch {
        throw new ApiError(400, "Invalid JSON");
      }

      if (pathname === "/api/create-order") {
        if (body && body.product_id) {
          const catalog = await loadCatalog(env.DIGITAL_CATALOG_URL, fetchImpl);
          return json(200, await createDigitalOrder(body, env, catalog, fetchImpl));
        }
        const catalog = await loadCatalog(env.CATALOG_URL, fetchImpl);
        return json(200, await createOrder(String(body.service_id || ""), env, catalog, fetchImpl));
      }
      if (pathname === "/api/verify-payment") return json(200, await verifyPayment(body, env));
      throw new ApiError(404, "Not found");
    } catch (err) {
      const status = err instanceof ApiError ? err.status : 500;
      const data = { error: err instanceof ApiError ? err.message : "Server error" };
      if (pathname === "/api/verify-payment") data.verified = false;
      return json(status, data);
    }
  },
};
