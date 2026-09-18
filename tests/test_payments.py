#!/usr/bin/env python3
"""Unit tests for the local checkout API (scripts/dev_server.py). No network, no real keys.  python3 tests/test_payments.py"""
import hashlib
import hmac
import importlib.util
import io
import json
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

spec = importlib.util.spec_from_file_location("dev_server", Path(__file__).resolve().parent.parent / "scripts" / "dev_server.py")
ds = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ds)

SECRET = "unit_test_secret"
FUTURE = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
PAST = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()


def catalog(**offer):
    base = {"id": "founding-10", "active": True, "ends_at": FUTURE, "slots_left": 5}
    base.update(offer)
    return {"currency": "INR", "offer": base, "items": {"svc": {"name": "Founding 10 — Svc", "amount_paise": 149900}, "tiny": {"name": "Tiny", "amount_paise": 50}}}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class CreateOrderTests(unittest.TestCase):
    def test_success_uses_server_side_amount(self):
        sent = {}

        def opener(req, timeout):
            sent["body"] = json.loads(req.data)
            sent["auth"] = req.headers["Authorization"]
            return FakeResponse(json.dumps({"id": "order_123", "amount": 149900, "currency": "INR"}).encode())

        out = ds.create_order("svc", "rzp_test_key", SECRET, catalog(), opener)
        self.assertEqual(out["order_id"], "order_123")
        self.assertEqual(sent["body"]["amount"], 149900)
        self.assertTrue(sent["auth"].startswith("Basic "))
        self.assertEqual(out["key_id"], "rzp_test_key")
        self.assertNotIn(SECRET, json.dumps(out))

    def test_unknown_service(self):
        with self.assertRaises(ds.ApiError) as cm:
            ds.create_order("nope", "k", SECRET, catalog(), None)
        self.assertEqual(cm.exception.status, 400)

    def test_minimum_amount(self):
        with self.assertRaises(ds.ApiError) as cm:
            ds.create_order("tiny", "k", SECRET, catalog(), None)
        self.assertEqual(cm.exception.status, 400)

    def test_offer_expired_or_sold_out(self):
        for cat in (catalog(ends_at=PAST), catalog(slots_left=0), catalog(active=False)):
            with self.assertRaises(ds.ApiError) as cm:
                ds.create_order("svc", "k", SECRET, cat, None)
            self.assertEqual(cm.exception.status, 409)

    def test_auth_failure_maps_to_401(self):
        def opener(req, timeout):
            raise urllib.error.HTTPError(ds.ORDERS_URL, 401, "Unauthorized", {}, None)

        with self.assertRaises(ds.ApiError) as cm:
            ds.create_order("svc", "k", SECRET, catalog(), opener)
        self.assertEqual(cm.exception.status, 401)

    def test_razorpay_error_maps_to_500(self):
        def opener(req, timeout):
            raise urllib.error.HTTPError(ds.ORDERS_URL, 400, "Bad Request", {}, None)

        with self.assertRaises(ds.ApiError) as cm:
            ds.create_order("svc", "k", SECRET, catalog(), opener)
        self.assertEqual(cm.exception.status, 500)


class VerifyTests(unittest.TestCase):
    def body(self, signature=None):
        sig = signature or hmac.new(SECRET.encode(), b"order_1|pay_1", hashlib.sha256).hexdigest()
        return {"razorpay_order_id": "order_1", "razorpay_payment_id": "pay_1", "razorpay_signature": sig}

    def test_valid_signature(self):
        self.assertTrue(ds.verify_payment(self.body(), SECRET)["verified"])

    def test_signature_mismatch_is_400(self):
        with self.assertRaises(ds.ApiError) as cm:
            ds.verify_payment(self.body("0" * 64), SECRET)
        self.assertEqual(cm.exception.status, 400)

    def test_missing_fields_is_400(self):
        with self.assertRaises(ds.ApiError) as cm:
            ds.verify_payment({"razorpay_order_id": "order_1"}, SECRET)
        self.assertEqual(cm.exception.status, 400)


DEP_CATALOG = {"currency": "INR", "deposits": {
    "card": {"name": "Digital Visiting Card", "total_paise": 49900, "deposit_paise": 25000, "balance_paise": 24900},
    "broken": {"name": "Broken", "total_paise": 1000, "deposit_paise": 600, "balance_paise": 600}}}
CUSTOMER = {"name": "Asha Verma", "phone": "+91 98765 43210", "email": "asha@example.com"}
ORDER_ID = "order_ABCDEFGHIJ1234"
NOTES = {"moodily_order_id": "MDLY-20260918-ABCDEF", "kind": "deposit", "service_id": "card", "service_name": "Digital Visiting Card",
         "total_paise": "49900", "deposit_paise": "25000", "balance_paise": "24900",
         "customer_name": "Asha", "customer_phone": "919876543210", "customer_email": "asha@example.com"}


def order_opener(order):
    def opener(req, timeout):
        return FakeResponse(json.dumps(order).encode())
    return opener


class DepositTests(unittest.TestCase):
    def test_deposit_split_and_client_amount_ignored(self):
        sent = {}

        def opener(req, timeout):
            sent["body"] = json.loads(req.data)
            return FakeResponse(json.dumps({"id": ORDER_ID, "amount": sent["body"]["amount"], "currency": "INR"}).encode())

        out = ds.create_deposit_order({"service_id": "card", "amount": 100, "customer": CUSTOMER}, "rzp_test_k", SECRET, DEP_CATALOG, opener)
        self.assertEqual(sent["body"]["amount"], 25000)
        self.assertEqual(sent["body"]["receipt"], out["moodily_order_id"])
        self.assertEqual(sent["body"]["notes"]["kind"], "deposit")
        self.assertEqual((out["amount"], out["total_paise"], out["balance_paise"]), (25000, 49900, 24900))
        self.assertEqual(out["prefill"]["contact"], "919876543210")
        self.assertNotIn(SECRET, json.dumps(out))

    def test_order_id_format_uses_ist_date(self):
        # 20:00 UTC on 17 Sep is 01:30 IST on 18 Sep
        oid = ds.moodily_order_id(datetime(2026, 9, 17, 20, 0, tzinfo=timezone.utc))
        self.assertRegex(oid, r"^MDLY-20260918-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{6}$")

    def test_invalid_service_customer_and_catalogue(self):
        cases = [({"service_id": "nope", "customer": CUSTOMER}, 400), ({"service_id": "broken", "customer": CUSTOMER}, 500),
                 ({"service_id": "card"}, 400), ({"service_id": "card", "customer": dict(CUSTOMER, name="A")}, 400),
                 ({"service_id": "card", "customer": dict(CUSTOMER, phone="123")}, 400),
                 ({"service_id": "card", "customer": dict(CUSTOMER, email="x")}, 400)]
        for body, status in cases:
            with self.assertRaises(ds.ApiError) as cm:
                ds.create_deposit_order(body, "k", SECRET, DEP_CATALOG, None)
            self.assertEqual(cm.exception.status, status, body)

    def test_mode_mismatch_and_live_guard(self):
        with self.assertRaises(ds.ApiError) as cm:
            ds.check_keys({"RAZORPAY_KEY_ID": "rzp_test_x", "RAZORPAY_KEY_SECRET": "s", "PAYMENT_MODE": "live"})
        self.assertEqual(cm.exception.status, 500)
        with self.assertRaises(ds.ApiError) as cm:
            ds.check_keys({"RAZORPAY_KEY_ID": "rzp_live_x", "RAZORPAY_KEY_SECRET": "s"})
        self.assertEqual(cm.exception.status, 403)
        self.assertEqual(ds.check_keys({"RAZORPAY_KEY_ID": "rzp_test_x", "RAZORPAY_KEY_SECRET": "s", "PAYMENT_MODE": "test"})[0], "rzp_test_x")

    def test_verify_returns_summary_without_pii(self):
        sig = hmac.new(SECRET.encode(), "{}|pay_1".format(ORDER_ID).encode(), hashlib.sha256).hexdigest()
        body = {"razorpay_order_id": ORDER_ID, "razorpay_payment_id": "pay_1", "razorpay_signature": sig}
        out = ds.verify_deposit(body, "k", SECRET, order_opener({"id": ORDER_ID, "amount": 25000, "status": "paid", "notes": NOTES}))
        self.assertTrue(out["verified"])
        self.assertEqual(out["moodily_order_id"], "MDLY-20260918-ABCDEF")
        self.assertNotRegex(json.dumps(out), r"(?i)asha|98765")
        with self.assertRaises(ds.ApiError):
            ds.verify_deposit(dict(body, razorpay_signature="f" * 64), "k", SECRET, None)

    def test_status_no_pii_and_deposit_only(self):
        out = ds.deposit_status(ORDER_ID, "k", SECRET, order_opener({"id": ORDER_ID, "amount": 25000, "status": "paid", "notes": NOTES}))
        self.assertTrue(out["paid"])
        self.assertNotRegex(json.dumps(out), r"(?i)asha")
        pending = ds.deposit_status(ORDER_ID, "k", SECRET, order_opener({"id": ORDER_ID, "status": "attempted", "notes": NOTES}))
        self.assertFalse(pending["paid"])
        for oid, order, status in ((ORDER_ID, {"id": ORDER_ID, "status": "paid", "notes": {"offer_id": "founding-10"}}, 404),
                                   ("../payments", {}, 400), ("order_short", {}, 400)):
            with self.assertRaises(ds.ApiError) as cm:
                ds.deposit_status(oid, "k", SECRET, order_opener(order))
            self.assertEqual(cm.exception.status, status)

    def test_webhook_signature_and_retry(self):
        raw = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {"order_id": ORDER_ID, "notes": {"moodily_order_id": "MDLY-20260918-ABCDEF"}}}}}).encode()
        whs = "unit_webhook_secret"
        sig = hmac.new(whs.encode(), raw, hashlib.sha256).hexdigest()
        first, retry = ds.handle_webhook(raw, sig, whs), ds.handle_webhook(raw, sig, whs)
        self.assertEqual(first, retry)
        self.assertEqual(first["moodily_order_id"], "MDLY-20260918-ABCDEF")
        for s, secret, status in (("0" * 64, whs, 400), (None, whs, 400), (sig, "", 500),
                                  (hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest(), whs, 400)):
            with self.assertRaises(ds.ApiError) as cm:
                ds.handle_webhook(raw, s, secret)
            self.assertEqual(cm.exception.status, status)

    def test_health_never_contains_values(self):
        env = {"RAZORPAY_KEY_ID": "rzp_test_abc", "RAZORPAY_KEY_SECRET": "sek", "RAZORPAY_WEBHOOK_SECRET": "whsek", "PAYMENT_MODE": "test"}
        ds._GATEWAY.update(at=0, ok=False, key="")
        out = ds.health(env, opener=lambda req, timeout: FakeResponse(b"{}"))
        self.assertTrue(out["mode_matches_key"] and out["webhook_secret_configured"] and out["ready"])
        ds._GATEWAY.update(at=0, ok=False, key="")

        def denied(req, timeout):
            raise urllib.error.HTTPError(ds.ORDERS_URL, 401, "Unauthorized", {}, None)
        self.assertFalse(ds.health(env, opener=denied)["ready"])
        self.assertFalse(ds.health(dict(env, PAYMENT_MODE="live"), opener=denied)["ready"])
        for v in env.values():
            if v != "test":
                self.assertNotIn(v, json.dumps(out))


if __name__ == "__main__":
    unittest.main(verbosity=1)
