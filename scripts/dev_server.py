#!/usr/bin/env python3
"""Local dev server: serves the built site AND the Razorpay checkout API.

Same contract as worker/src/index.js (production). Reads RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET
(/ RAZORPAY_WEBHOOK_SECRET / PAYMENT_MODE) from .env, or from the file named by MOODILY_ENV_FILE
(use that to test with test keys without touching .env).

    MOODILY_SHOW_TEST_PAYMENTS=1 MOODILY_CHECKOUT_API=/ python3 build.py   # preview build with pay buttons (do not commit)
    python3 scripts/dev_server.py                                           # http://localhost:8124
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "assets" / "data" / "checkout-prices.json"
ORDERS_URL = "https://api.razorpay.com/v1/orders"
MIN_AMOUNT_PAISE = 100
ORDER_ID_RE = re.compile(r"^order_[A-Za-z0-9]{14}$")
ID_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"  # no 0/O/1/I/L
IST = timezone(timedelta(hours=5, minutes=30))
PAID_STATUS = "DEPOSIT PAID — BRIEF PENDING"


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def load_env(path=None):
    path = Path(path or os.environ.get("MOODILY_ENV_FILE") or ROOT / ".env")
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def resolve_item(catalog, service_id, now=None):
    item = (catalog.get("items") or {}).get(service_id)
    if not item:
        raise ApiError(400, "Unknown service")
    offer = catalog.get("offer") or {}
    now = now or datetime.now(timezone.utc)
    if not offer.get("active") or offer.get("slots_left", 0) <= 0 or now > datetime.fromisoformat(offer["ends_at"]):
        raise ApiError(409, "यह offer समाप्त हो गया है।")
    amount = item.get("amount_paise")
    if not isinstance(amount, int) or amount < MIN_AMOUNT_PAISE:
        raise ApiError(400, "Amount must be at least 100 paise")
    return item, offer


def create_order(service_id, key_id, key_secret, catalog, opener=urllib.request.urlopen):
    item, offer = resolve_item(catalog, service_id)
    payload = {
        "amount": item["amount_paise"],
        "currency": catalog.get("currency", "INR"),
        "receipt": "{}-{:x}".format(offer["id"], int(time.time() * 1000))[:40],
        "notes": {"service_id": service_id, "offer_id": offer["id"]},
    }
    auth = base64.b64encode("{}:{}".format(key_id, key_secret).encode()).decode()
    req = urllib.request.Request(ORDERS_URL, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": "Basic " + auth})
    try:
        with opener(req, timeout=15) as resp:
            order = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise ApiError(401, "Payment gateway authentication failed")
        raise ApiError(500, "Could not create order")
    except (urllib.error.URLError, OSError, ValueError):
        raise ApiError(500, "Could not create order")
    return {"order_id": order["id"], "amount": order["amount"], "currency": order["currency"],
            "key_id": key_id, "name": "Moodily", "description": item["name"]}


def verify_signature(order_id, payment_id, signature, key_secret):
    expected = hmac.new(key_secret.encode(), "{}|{}".format(order_id, payment_id).encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_payment(body, key_secret):
    fields = ("razorpay_order_id", "razorpay_payment_id", "razorpay_signature")
    if not all(isinstance(body.get(f), str) and body.get(f) for f in fields):
        raise ApiError(400, "Missing payment fields")
    if not verify_signature(body["razorpay_order_id"], body["razorpay_payment_id"], body["razorpay_signature"], key_secret):
        raise ApiError(400, "Payment signature verification failed")
    return {"verified": True, "order_id": body["razorpay_order_id"], "payment_id": body["razorpay_payment_id"]}


def key_mode(key_id):
    return "live" if (key_id or "").startswith("rzp_live_") else "test" if (key_id or "").startswith("rzp_test_") else "unknown"


def _auth(key_id, key_secret):
    return "Basic " + base64.b64encode("{}:{}".format(key_id, key_secret).encode()).decode()


def _rzp(req, opener, fail_status=500, fail_msg="Could not create order"):
    try:
        with opener(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise ApiError(401, "Payment gateway authentication failed")
        if exc.code in (400, 404) and req.get_method() == "GET":
            raise ApiError(404, "Order not found")
        raise ApiError(fail_status, fail_msg)
    except (urllib.error.URLError, OSError, ValueError):
        raise ApiError(fail_status, fail_msg)


def moodily_order_id(now=None):
    day = (now or datetime.now(timezone.utc)).astimezone(IST).strftime("%Y%m%d")
    return "MDLY-{}-{}".format(day, "".join(secrets.choice(ID_ALPHABET) for _ in range(6)))


def clean_customer(c):
    c = c if isinstance(c, dict) else {}
    name = re.sub(r"[\x00-\x1f]", "", str(c.get("name") or "")).strip()
    phone = re.sub(r"[\s()+-]", "", str(c.get("phone") or ""))
    email = str(c.get("email") or "").strip()
    if not 2 <= len(name) <= 80:
        raise ApiError(400, "कृपया अपना नाम लिखें")
    if not re.fullmatch(r"\d{10,13}", phone):
        raise ApiError(400, "कृपया सही WhatsApp number लिखें")
    if len(email) > 120 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ApiError(400, "कृपया सही email लिखें")
    return {"name": name, "phone": phone, "email": email}


def resolve_deposit(catalog, service_id):
    item = (catalog.get("deposits") or {}).get(service_id)
    if not item:
        raise ApiError(400, "यह service अभी online deposit के लिए उपलब्ध नहीं — exact quote लें")
    vals = [item.get(k) for k in ("total_paise", "deposit_paise", "balance_paise")]
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in vals) or vals[1] < MIN_AMOUNT_PAISE or vals[1] + vals[2] != vals[0]:
        raise ApiError(500, "Price catalogue is inconsistent")
    return item


def _summary(notes, amount=0):
    def num(k):
        try:
            return int(notes.get(k) or 0)
        except (TypeError, ValueError):
            return 0
    return {"moodily_order_id": notes.get("moodily_order_id", ""), "service_id": notes.get("service_id", ""),
            "service_name": notes.get("service_name", ""), "total_paise": num("total_paise"),
            "deposit_paise": num("deposit_paise") or amount or 0, "balance_paise": num("balance_paise")}


def create_deposit_order(body, key_id, key_secret, catalog, opener=urllib.request.urlopen, now=None):
    service_id = str((body or {}).get("service_id") or "")
    item = resolve_deposit(catalog, service_id)  # any client "amount" is ignored on purpose
    customer = clean_customer((body or {}).get("customer"))
    moid = moodily_order_id(now)
    notes = {"moodily_order_id": moid, "kind": "deposit", "service_id": service_id, "service_name": item["name"][:250],
             "total_paise": str(item["total_paise"]), "deposit_paise": str(item["deposit_paise"]),
             "balance_paise": str(item["balance_paise"]), "customer_name": customer["name"],
             "customer_phone": customer["phone"], "customer_email": customer["email"]}
    payload = {"amount": item["deposit_paise"], "currency": catalog.get("currency", "INR"), "receipt": moid, "notes": notes}
    req = urllib.request.Request(ORDERS_URL, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": _auth(key_id, key_secret)})
    order = _rzp(req, opener)
    out = {"order_id": order["id"], "moodily_order_id": moid, "amount": order["amount"], "currency": order["currency"],
           "key_id": key_id, "name": "Moodily", "description": "{} — 50% advance".format(item["name"])}
    out.update(_summary(notes))
    out["prefill"] = {"name": customer["name"], "email": customer["email"], "contact": customer["phone"]}
    return out


def fetch_order(order_id, key_id, key_secret, opener=urllib.request.urlopen):
    if not ORDER_ID_RE.match(order_id or ""):
        raise ApiError(400, "Invalid order id")
    req = urllib.request.Request("{}/{}".format(ORDERS_URL, order_id), headers={"Authorization": _auth(key_id, key_secret)})
    return _rzp(req, opener, 502, "Could not reach payment gateway")


def verify_deposit(body, key_id, key_secret, opener=urllib.request.urlopen):
    base = verify_payment(body, key_secret)  # HMAC is the authority
    try:
        order = fetch_order(base["order_id"], key_id, key_secret, opener)
        base.update(_summary(order.get("notes") or {}, order.get("amount")))
    except ApiError:
        pass
    base["status"] = PAID_STATUS
    return base


def deposit_status(order_id, key_id, key_secret, opener=urllib.request.urlopen):
    """Resume/refresh. No personal data: an order id alone never reveals a customer."""
    order = fetch_order(order_id, key_id, key_secret, opener)
    notes = order.get("notes") or {}
    if not isinstance(notes, dict) or notes.get("kind") != "deposit":
        raise ApiError(404, "Order not found")
    paid = order.get("status") == "paid"
    out = {"order_id": order["id"], "paid": paid, "status": PAID_STATUS if paid else "PAYMENT PENDING"}
    out.update(_summary(notes, order.get("amount")))
    return out


def handle_webhook(raw, signature, webhook_secret):
    """No side effects, so a retried delivery is naturally idempotent."""
    if not webhook_secret:
        raise ApiError(500, "Webhook secret not configured")
    if not signature:
        raise ApiError(400, "Missing webhook signature")
    expected = hmac.new(webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise ApiError(400, "Webhook signature verification failed")
    try:
        event = json.loads(raw)
    except ValueError:
        raise ApiError(400, "Invalid JSON")
    payload = event.get("payload") or {}
    payment = (payload.get("payment") or {}).get("entity") or {}
    order = (payload.get("order") or {}).get("entity") or {}
    notes = order.get("notes") or payment.get("notes") or {}
    return {"received": True, "event": str(event.get("event") or ""), "order_id": order.get("id") or payment.get("order_id") or "",
            "moodily_order_id": notes.get("moodily_order_id", "") if isinstance(notes, dict) else ""}


def health(env=os.environ):
    kid = env.get("RAZORPAY_KEY_ID") or ""
    try:
        cat = json.loads(CATALOG.read_text(encoding="utf-8"))
        reachable, count = True, len(cat.get("deposits") or {})
    except (OSError, ValueError):
        reachable, count = False, 0
    expected = env.get("PAYMENT_MODE") or ""
    return {"service": "moodily-payments (local)", "expected_mode": expected or "unset", "key_mode": key_mode(kid),
            "key_id_configured": bool(kid), "key_secret_configured": bool(env.get("RAZORPAY_KEY_SECRET")),
            "webhook_secret_configured": bool(env.get("RAZORPAY_WEBHOOK_SECRET")),
            "mode_matches_key": not expected or expected == key_mode(kid), "catalogue_reachable": reachable,
            "deposit_services": count, "order_endpoint": "/api/payment/create-order",
            "verify_endpoint": "/api/payment/verify", "webhook_endpoint": "/api/payment/webhook"}


def check_keys(env=os.environ):
    key_id, key_secret = env.get("RAZORPAY_KEY_ID"), env.get("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret:
        raise ApiError(500, "Payment server not configured (.env missing)")
    if env.get("PAYMENT_MODE") and env.get("PAYMENT_MODE") != key_mode(key_id):
        raise ApiError(500, "Payment mode mismatch — server key does not match PAYMENT_MODE")
    if key_id.startswith("rzp_live_") and env.get("MOODILY_ALLOW_LIVE_LOCAL") != "1":
        # A local "test" with live keys creates a real order and charges a real card.
        raise ApiError(403, "Live Razorpay keys are loaded — local checkout is disabled to avoid real charges. "
                            "Use test keys (MOODILY_ENV_FILE), or set MOODILY_ALLOW_LIVE_LOCAL=1 for one deliberate live test.")
    return key_id, key_secret


class Handler(SimpleHTTPRequestHandler):
    def _blocked(self):
        # Never serve dotfiles (.env) or source folders from the dev server.
        parts = self.path.split("?")[0].split("/")
        return any(p.startswith(".") for p in parts if p) or parts[1:2] in (["src"], ["worker"], ["scripts"], ["tests"], ["_project"])

    def do_GET(self):
        path = self.path.split("?")[0]
        if path.startswith("/api/"):
            try:
                if path == "/api/payment/health":
                    return self._json(200, health())
                m = re.fullmatch(r"/api/payment/status/([^/]+)", path)
                if not m:
                    raise ApiError(404, "Not found")
                key_id, key_secret = check_keys()
                return self._json(200, deposit_status(urllib.parse.unquote(m.group(1)), key_id, key_secret))
            except ApiError as exc:
                return self._json(exc.status, {"error": exc.message})
        if self._blocked():
            return self.send_error(404)
        return super().do_GET()

    def do_HEAD(self):
        if self._blocked():
            return self.send_error(404)
        return super().do_HEAD()

    def do_POST(self):
        path = self.path.split("?")[0]
        routes = ("/api/create-order", "/api/verify-payment", "/api/payment/create-order", "/api/payment/verify", "/api/payment/webhook")
        try:
            if path not in routes:
                raise ApiError(404, "Not found")
            length = min(int(self.headers.get("Content-Length") or 0), 100000)
            raw = self.rfile.read(length) or b"{}"
            if path == "/api/payment/webhook":
                # raw body: the signature covers the exact bytes Razorpay sent. Never log the signature.
                return self._json(200, handle_webhook(raw, self.headers.get("X-Razorpay-Signature"),
                                                      os.environ.get("RAZORPAY_WEBHOOK_SECRET")))
            key_id, key_secret = check_keys()
            try:
                body = json.loads(raw)
                if not isinstance(body, dict):
                    raise ValueError
            except ValueError:
                raise ApiError(400, "Invalid JSON")
            if path == "/api/payment/create-order":
                catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
                self._json(200, create_deposit_order(body, key_id, key_secret, catalog))
            elif path == "/api/payment/verify":
                self._json(200, verify_deposit(body, key_id, key_secret))
            elif path == "/api/create-order":
                catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
                self._json(200, create_order(str(body.get("service_id", "")), key_id, key_secret, catalog))
            else:
                self._json(200, verify_payment(body, key_secret))
        except ApiError as exc:
            data = {"error": exc.message}
            if path in ("/api/verify-payment", "/api/payment/verify"):
                data["verified"] = False
            self._json(exc.status, data)

    def log_message(self, fmt, *args):
        # keep request lines but drop query strings (never log customer data or ids beyond the path)
        sys.stderr.write("%s - %s\n" % (self.address_string(), (fmt % args).split("?")[0]))

    def _json(self, status, data):
        raw = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Robots-Tag", "noindex")
        self.end_headers()
        self.wfile.write(raw)


def main():
    load_env()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8124
    kid = os.environ.get("RAZORPAY_KEY_ID") or ""
    mode = ("LIVE — real charges" + (" (ALLOWED by MOODILY_ALLOW_LIVE_LOCAL=1)" if os.environ.get("MOODILY_ALLOW_LIVE_LOCAL") == "1"
                                     else ", local checkout BLOCKED") if kid.startswith("rzp_live_")
            else "test" if kid.startswith("rzp_test_") else "")
    # prints the mode only — never the key or secret
    print("Moodily dev server: http://localhost:{} · Razorpay keys {}".format(
        port, ("loaded, " + mode) if kid and os.environ.get("RAZORPAY_KEY_SECRET") else "MISSING — create .env"), flush=True)
    print("  webhook secret {} · PAYMENT_MODE {}".format(
        "set" if os.environ.get("RAZORPAY_WEBHOOK_SECRET") else "not set", os.environ.get("PAYMENT_MODE") or "unset"), flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=str(ROOT))).serve_forever()


if __name__ == "__main__":
    main()
