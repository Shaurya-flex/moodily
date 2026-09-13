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


if __name__ == "__main__":
    unittest.main(verbosity=1)
