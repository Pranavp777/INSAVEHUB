"""Tests for Donation order creation, anonymous option, and HMAC-SHA256 payment verification."""
import hashlib
import hmac
import json

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.donations.models import Donation


class DonationSystemTests(TestCase):
    def setUp(self) -> None:
        cache.clear()

    @override_settings(RAZORPAY_KEY_SECRET="test_webhook_and_key_secret_999")
    def test_donation_creation_anonymous_and_hmac_verification(self) -> None:
        # 1. Create an anonymous donation order
        create_resp = self.client.post(
            reverse("donations:create"),
            data=json.dumps(
                {
                    "amount": "500",
                    "donor_name": "Hidden Donor",
                    "donor_email": "supporter@example.com",
                    "message": "Supporting edge infrastructure.",
                    "is_anonymous": True,
                }
            ),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(create_resp.status_code, 200)
        order_data = create_resp.json()["order"]
        donation = Donation.objects.get(id=order_data["donation_id"])
        self.assertTrue(donation.is_anonymous)
        self.assertEqual(donation.public_donor_label, "Anonymous Supporter")
        self.assertEqual(donation.status, Donation.Status.CREATED)

        # 2. Invalid signature is rejected and never fakes confirmation
        bad_verify = self.client.post(
            reverse("donations:verify"),
            data=json.dumps(
                {
                    "razorpay_order_id": donation.provider_order_id,
                    "razorpay_payment_id": "pay_fake123",
                    "razorpay_signature": "invalid_hex_signature",
                }
            ),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(bad_verify.status_code, 400)
        donation.refresh_from_db()
        self.assertEqual(donation.status, Donation.Status.FAILED)

        # 3. Valid HMAC-SHA256 signature marks donation COMPLETED
        payment_id = "pay_verified_98765"
        valid_sig = hmac.new(
            b"test_webhook_and_key_secret_999",
            f"{donation.provider_order_id}|{payment_id}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        good_verify = self.client.post(
            reverse("donations:verify"),
            data=json.dumps(
                {
                    "razorpay_order_id": donation.provider_order_id,
                    "razorpay_payment_id": payment_id,
                    "razorpay_signature": valid_sig,
                }
            ),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(good_verify.status_code, 200)
        donation.refresh_from_db()
        self.assertEqual(donation.status, Donation.Status.COMPLETED)
