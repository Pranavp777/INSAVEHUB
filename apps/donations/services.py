"""
Payment gateway and Razorpay integration service for InSave Hub donations.
Reads credentials strictly from environment variables and enforces HMAC-SHA256
signature verification before marking any contribution completed.
"""
import hashlib
import hmac
import secrets
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional, Tuple

import requests
from django.conf import settings
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from apps.core.models import AuditLog, SiteConfiguration
from apps.core.utils import get_ip_hash
from apps.donations.models import Donation

RAZORPAY_ORDERS_URL = "https://api.razorpay.com/v1/orders"


class DonationError(Exception):
    """Raised when a donation creation or verification operation fails."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def is_razorpay_configured() -> bool:
    key_id = getattr(settings, "RAZORPAY_KEY_ID", "").strip()
    key_secret = getattr(settings, "RAZORPAY_KEY_SECRET", "").strip()
    return bool(key_id and key_secret)


@transaction.atomic
def create_donation_order(
    request: HttpRequest,
    raw_amount: Any,
    donor_name: str = "",
    donor_email: str = "",
    message: str = "",
    is_anonymous: bool = False,
) -> Tuple[Donation, Dict[str, Any]]:
    """
    Validate donation parameters, create a Donation record in `created` status,
    and initialize a Razorpay order when gateway credentials are configured.
    """
    config = SiteConfiguration.get_solo()
    if not config.enable_donations:
        raise DonationError("donations_disabled", "Donations are currently disabled.")

    try:
        amount = Decimal(str(raw_amount).strip()).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise DonationError("invalid_amount", "Please enter a valid numeric donation amount.") from exc

    min_amt = Decimal(str(config.minimum_donation_amount))
    max_amt = Decimal(str(config.maximum_donation_amount))
    if amount < min_amt or amount > max_amt:
        raise DonationError(
            "amount_out_of_bounds",
            f"Donation amount must be between {config.donation_currency} {min_amt} and {config.donation_currency} {max_amt}.",
        )

    user = request.user if (hasattr(request, "user") and request.user.is_authenticated) else None
    clean_name = (donor_name or "").strip()[:120]
    clean_email = (donor_email or "").strip()[:254]
    clean_message = (message or "").strip()[:280]

    if user and not clean_name and not is_anonymous:
        clean_name = user.get_full_name() or user.username
    if user and not clean_email:
        clean_email = user.email or ""

    amount_subunits = int(amount * 100)  # Paise for INR
    receipt_ref = f"insave_{secrets.token_hex(8)}"
    provider_order_id = f"order_{secrets.token_hex(12)}"
    gateway_live = False

    key_id = getattr(settings, "RAZORPAY_KEY_ID", "").strip()
    key_secret = getattr(settings, "RAZORPAY_KEY_SECRET", "").strip()

    if key_id and key_secret:
        try:
            resp = requests.post(
                RAZORPAY_ORDERS_URL,
                auth=(key_id, key_secret),
                json={
                    "amount": amount_subunits,
                    "currency": config.donation_currency,
                    "receipt": receipt_ref,
                    "notes": {
                        "platform": "InSave Hub",
                        "anonymous": str(bool(is_anonymous)),
                    },
                },
                timeout=10,
            )
            if resp.status_code == 200:
                order_data = resp.json()
                provider_order_id = order_data.get("id", provider_order_id)
                gateway_live = True
            else:
                raise DonationError(
                    "gateway_order_failed",
                    "Payment provider rejected order initialization. Please verify gateway credentials.",
                )
        except requests.RequestException as exc:
            raise DonationError(
                "gateway_unreachable",
                "Unable to connect to the payment provider at this moment.",
            ) from exc

    donation = Donation.objects.create(
        user=user,
        donor_name="Anonymous" if is_anonymous else clean_name,
        donor_email=clean_email,
        is_anonymous=bool(is_anonymous),
        amount=amount,
        currency=config.donation_currency,
        message=clean_message,
        provider=Donation.Provider.RAZORPAY,
        provider_order_id=provider_order_id,
        status=Donation.Status.CREATED,
        ip_hash=get_ip_hash(request),
    )

    AuditLog.record(
        event_type="donation.order_created",
        description=f"Created donation order {provider_order_id} for {config.donation_currency} {amount}.",
        request=request,
        resource_type="Donation",
        resource_id=str(donation.id),
    )

    checkout_payload = {
        "donation_id": str(donation.id),
        "provider_order_id": donation.provider_order_id,
        "amount": str(donation.amount),
        "amount_subunits": amount_subunits,
        "currency": donation.currency,
        "razorpay_key_id": key_id,
        "gateway_live": gateway_live,
        "donor_name": donation.public_donor_label,
        "donor_email": donation.donor_email,
    }
    return donation, checkout_payload


@transaction.atomic
def verify_razorpay_payment_signature(
    request: Optional[HttpRequest],
    provider_order_id: str,
    provider_payment_id: str,
    provider_signature: str,
) -> Tuple[bool, str, Optional[Donation]]:
    """
    Cryptographically verify Razorpay's HMAC-SHA256 signature (`order_id|payment_id`)
    using `RAZORPAY_KEY_SECRET` before marking a Donation as `completed`.
    Never marks a payment completed without a valid cryptographic signature.
    """
    key_secret = getattr(settings, "RAZORPAY_KEY_SECRET", "").strip()
    if not key_secret:
        return (
            False,
            "Payment gateway secret is not configured in environment variables; signature cannot be verified.",
            None,
        )

    if not provider_order_id or not provider_payment_id or not provider_signature:
        return False, "Missing payment verification parameters.", None

    try:
        donation = Donation.objects.select_for_update().get(provider_order_id=provider_order_id)
    except Donation.DoesNotExist:
        return False, "Matching donation order not found.", None

    if donation.status == Donation.Status.COMPLETED:
        return True, "Donation payment was already verified.", donation

    msg = f"{provider_order_id}|{provider_payment_id}".encode("utf-8")
    expected_sig = hmac.new(
        key_secret.encode("utf-8"),
        msg,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, provider_signature):
        donation.status = Donation.Status.FAILED
        donation.save(update_fields=["status"])
        AuditLog.record(
            event_type="donation.signature_invalid",
            description=f"Invalid HMAC signature for donation order {provider_order_id}.",
            request=request,
            severity=AuditLog.Severity.ERROR,
            resource_type="Donation",
            resource_id=str(donation.id),
        )
        return False, "Payment signature verification failed.", donation

    donation.provider_payment_id = provider_payment_id
    donation.provider_signature = provider_signature
    donation.status = Donation.Status.COMPLETED
    donation.completed_at = timezone.now()
    donation.save(
        update_fields=["provider_payment_id", "provider_signature", "status", "completed_at"]
    )

    AuditLog.record(
        event_type="donation.completed",
        description=f"Verified payment {provider_payment_id} for donation {donation.id}.",
        request=request,
        resource_type="Donation",
        resource_id=str(donation.id),
    )
    return True, "Thank you. Your contribution has been cryptographically verified.", donation
