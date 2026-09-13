#!/usr/bin/env python3
"""Local dev server: serves the built site AND the Razorpay checkout API.

Same contract as worker/src/index.js (production). Reads RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET from .env.

    MOODILY_SHOW_TEST_PAYMENTS=1 MOODILY_CHECKOUT_API=/ python3 build.py   # preview build with pay buttons (do not commit)
    python3 scripts/dev_server.py                                           # http://localhost:8124
"""
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "assets" / "data" / "checkout-prices.json"
ORDERS_URL = "https://api.razorpay.com/v1/orders"
MIN_AMOUNT_PAISE = 100


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def load_env(path=ROOT / ".env"):
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


class Handler(SimpleHTTPRequestHandler):
    def _blocked(self):
        # Never serve dotfiles (.env) or source folders from the dev server.
        parts = self.path.split("?")[0].split("/")
        return any(p.startswith(".") for p in parts if p) or parts[1:2] in (["src"], ["worker"], ["scripts"], ["tests"], ["_project"])

    def do_GET(self):
        if self._blocked():
            return self.send_error(404)
        return super().do_GET()

    def do_HEAD(self):
        if self._blocked():
            return self.send_error(404)
        return super().do_HEAD()

    def do_POST(self):
        path = self.path.split("?")[0]
        try:
            key_id, key_secret = os.environ.get("RAZORPAY_KEY_ID"), os.environ.get("RAZORPAY_KEY_SECRET")
            if path not in ("/api/create-order", "/api/verify-payment"):
                raise ApiError(404, "Not found")
            if not key_id or not key_secret:
                raise ApiError(500, "Payment server not configured (.env missing)")
            length = min(int(self.headers.get("Content-Length") or 0), 10000)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                raise ApiError(400, "Invalid JSON")
            if path == "/api/create-order":
                catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
                self._json(200, create_order(str(body.get("service_id", "")), key_id, key_secret, catalog))
            else:
                self._json(200, verify_payment(body, key_secret))
        except ApiError as exc:
            data = {"error": exc.message}
            if path == "/api/verify-payment":
                data["verified"] = False
            self._json(exc.status, data)

    def _json(self, status, data):
        raw = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def main():
    load_env()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8124
    print("Moodily dev server: http://localhost:{} · Razorpay keys {}".format(
        port, "loaded" if os.environ.get("RAZORPAY_KEY_ID") and os.environ.get("RAZORPAY_KEY_SECRET") else "MISSING — create .env"))
    ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=str(ROOT))).serve_forever()


if __name__ == "__main__":
    main()
