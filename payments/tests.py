import json
from unittest import mock

import razorpay
from django.core.cache import cache
from django.test import TestCase, override_settings

from packages.models import Package
from .models import Payment


@override_settings(RAZORPAY_KEY_ID="rzp_test_key", RAZORPAY_KEY_SECRET="secret", RAZORPAY_WEBHOOK_SECRET="whsec")
class PaymentTests(TestCase):
    def setUp(self):
        cache.clear()
        self.package = Package.objects.create(name="Starter", price=2999, duration=30)
        self.payment = Payment.objects.create(
            package=self.package,
            buyer_name="Asha",
            buyer_email="asha@example.com",
            razorpay_order_id="order_123",
            amount=2999,
        )

    def webhook(self, event, amount=299900):
        body = json.dumps({
            "event": event,
            "payload": {"payment": {"entity": {"id": "pay_1", "order_id": "order_123", "amount": amount}}},
        })
        return self.client.post(
            "/api/payments/webhook/", body, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE="sig"
        )

    @mock.patch("payments.views.get_client")
    def test_create_order(self, get_client):
        get_client.return_value.order.create.return_value = {"id": "order_new"}
        response = self.client.post(
            "/api/payments/create-order/",
            {"package_id": self.package.id, "name": "Asha", "email": "asha@example.com"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(get_client.return_value.order.create.call_args[0][0]["amount"], 299900)
        self.assertTrue(Payment.objects.filter(razorpay_order_id="order_new").exists())

    def test_create_order_rejects_invalid_email(self):
        response = self.client.post(
            "/api/payments/create-order/",
            {"package_id": self.package.id, "name": "Asha", "email": "nope"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    @mock.patch("payments.views.get_client")
    def test_verify_marks_paid(self, get_client):
        response = self.client.post(
            "/api/payments/verify/",
            {"razorpay_order_id": "order_123", "razorpay_payment_id": "pay_1", "razorpay_signature": "s"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "paid")

    @mock.patch("payments.views.get_client")
    def test_bad_verify_does_not_downgrade_paid(self, get_client):
        get_client.return_value.utility.verify_payment_signature.side_effect = (
            razorpay.errors.SignatureVerificationError("bad")
        )
        Payment.objects.filter(pk=self.payment.pk).update(status="paid")
        response = self.client.post(
            "/api/payments/verify/",
            {"razorpay_order_id": "order_123", "razorpay_payment_id": "pay_1", "razorpay_signature": "s"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "paid")

    @mock.patch("payments.views.get_client")
    def test_webhook_captured_marks_paid(self, get_client):
        response = self.webhook("payment.captured")
        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "paid")
        self.assertEqual(self.payment.razorpay_payment_id, "pay_1")

    @mock.patch("payments.views.get_client")
    def test_webhook_amount_mismatch_ignored(self, get_client):
        self.webhook("payment.captured", amount=100)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "created")

    @mock.patch("payments.views.get_client")
    def test_webhook_rejects_bad_signature(self, get_client):
        get_client.return_value.utility.verify_webhook_signature.side_effect = (
            razorpay.errors.SignatureVerificationError("bad")
        )
        response = self.webhook("payment.captured")
        self.assertEqual(response.status_code, 400)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "created")
