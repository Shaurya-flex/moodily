/**
 * Moodily payments API — Cloudflare Worker for Razorpay Standard Checkout.
 *
 *   POST /api/create-order   { service_id }                                   -> { order_id, amount, currency, key_id, name, description }
 *   POST /api/verify-payment { razorpay_order_id, razorpay_payment_id, razorpay_signature } -> { verified, order_id, payment_id }
 *
 * Same contract as scripts/dev_server.py (local testing).
 * Secrets: `wrangler secret put RAZORPAY_KEY_ID` and `wrangler secret put RAZORPAY_KEY_SECRET` — never in code or wrangler.toml.
 * Amounts are NEVER taken from the browser: they come from the catalogue that build.py publishes (CATALOG_URL).
 */
const ORDERS_URL = "https://api.razorpay.com/v1/orders";
const MIN_AMOUNT_PAISE = 100;

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

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
  const payload = {
    amount: item.amount_paise,
    currency: catalog.currency || "INR",
    receipt: `${offer.id}-${Date.now().toString(16)}`.slice(0, 40),
    notes: { service_id: serviceId, offer_id: offer.id },
  };
  let res;
  try {
    res = await fetchImpl(ORDERS_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Basic " + btoa(`${env.RAZORPAY_KEY_ID}:${env.RAZORPAY_KEY_SECRET}`),
      },
      body: JSON.stringify(payload),
    });
  } catch {
    throw new ApiError(500, "Could not create order");
  }
  if (res.status === 401) throw new ApiError(401, "Payment gateway authentication failed");
  if (!res.ok) throw new ApiError(500, "Could not create order");
  const order = await res.json();
  return {
    order_id: order.id,
    amount: order.amount,
    currency: order.currency,
    key_id: env.RAZORPAY_KEY_ID,
    name: "Moodily",
    description: item.name,
  };
}

export async function signatureFor(orderId, paymentId, secret) {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = await crypto.subtle.sign("HMAC", key, enc.encode(`${orderId}|${paymentId}`));
  return [...new Uint8Array(mac)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function safeEqual(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export async function verifyPayment(body, env) {
  const { razorpay_order_id: orderId, razorpay_payment_id: paymentId, razorpay_signature: signature } = body || {};
  if (![orderId, paymentId, signature].every((v) => typeof v === "string" && v)) {
    throw new ApiError(400, "Missing payment fields");
  }
  const expected = await signatureFor(orderId, paymentId, env.RAZORPAY_KEY_SECRET);
  if (!safeEqual(expected, signature)) throw new ApiError(400, "Payment signature verification failed");
  return { verified: true, order_id: orderId, payment_id: paymentId };
}

async function loadCatalog(env, fetchImpl) {
  const res = await fetchImpl(env.CATALOG_URL, { cf: { cacheTtl: 60 } });
  if (!res.ok) throw new ApiError(500, "Price catalogue unavailable");
  return res.json();
}

export default {
  async fetch(request, env, _ctx, fetchImpl = fetch) {
    const origin = request.headers.get("Origin") || "";
    const allowed = (env.ALLOWED_ORIGINS || "").split(",").map((s) => s.trim()).filter(Boolean);
    const cors = allowed.includes(origin)
      ? { "Access-Control-Allow-Origin": origin, "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "Content-Type", Vary: "Origin" }
      : {};
    const json = (status, data) => new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json", ...cors } });

    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
    const { pathname } = new URL(request.url);
    try {
      if (request.method !== "POST") throw new ApiError(405, "Method not allowed");
      if (!env.RAZORPAY_KEY_ID || !env.RAZORPAY_KEY_SECRET) throw new ApiError(500, "Payment server not configured");
      let body;
      try {
        body = await request.json();
      } catch {
        throw new ApiError(400, "Invalid JSON");
      }
      if (pathname === "/api/create-order") {
        const catalog = await loadCatalog(env, fetchImpl);
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
