"""Views and API endpoints for the Donation System."""
import json

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from apps.core.models import SiteConfiguration
from apps.core.rate_limit import rate_limit
from apps.core.utils import is_json_request
from apps.donations.models import Donation
from apps.donations.services import (
    DonationError,
    create_donation_order,
    is_razorpay_configured,
    verify_razorpay_payment_signature,
)


@require_GET
def donation_index_view(request: HttpRequest) -> HttpResponse:
    """Render the dedicated Glassmorphism Donation page."""
    config = SiteConfiguration.get_solo()
    preset_amounts = config.get_preset_amounts_list()

    user_donations = []
    if request.user.is_authenticated:
        user_donations = list(
            Donation.objects.filter(user=request.user).order_by("-created_at")[:10]
        )

    recent_verified = Donation.objects.filter(
        status=Donation.Status.COMPLETED
    ).order_by("-completed_at")[:6]

    return render(
        request,
        "donations/index.html",
        {
            "page_title": "Buy Us Cofee | InSave Hub",
            "meta_description": "Buy us a coffee to support InSave Hub.",
            "preset_amounts": preset_amounts,
            "user_donations": user_donations,
            "recent_verified": recent_verified,
            "gateway_configured": is_razorpay_configured(),
        },
    )


@require_POST
@rate_limit("donation", methods=("POST",))
def create_donation_view(request: HttpRequest) -> HttpResponse:
    """Initialize a one-time donation order (preset or custom amount)."""
    if request.content_type == "application/json":
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            payload = {}
        raw_amount = payload.get("amount")
        donor_name = str(payload.get("donor_name", "")).strip()
        donor_email = str(payload.get("donor_email", "")).strip()
        message = str(payload.get("message", "")).strip()
        is_anonymous = bool(payload.get("is_anonymous", False))
    else:
        raw_amount = request.POST.get("amount") or request.POST.get("custom_amount")
        donor_name = request.POST.get("donor_name", "").strip()
        donor_email = request.POST.get("donor_email", "").strip()
        message = request.POST.get("message", "").strip()
        is_anonymous = request.POST.get("is_anonymous") in ("on", "true", "1", "True")

    try:
        donation, checkout_payload = create_donation_order(
            request=request,
            raw_amount=raw_amount,
            donor_name=donor_name,
            donor_email=donor_email,
            message=message,
            is_anonymous=is_anonymous,
        )
    except DonationError as exc:
        if is_json_request(request):
            return JsonResponse(
                {
                    "status": "error",
                    "code": exc.code,
                    "message": exc.message,
                },
                status=400,
            )
        messages.error(request, exc.message)
        return redirect("donations:index")

    receipt_url = reverse("donations:receipt", kwargs={"donation_id": donation.id})
    checkout_payload["receipt_url"] = receipt_url

    if is_json_request(request):
        return JsonResponse(
            {
                "status": "ok",
                "message": "Donation order initialized.",
                "order": checkout_payload,
            }
        )

    messages.info(
        request,
        f"Donation order {donation.provider_order_id} created for {donation.currency} {donation.amount}.",
    )
    return redirect(receipt_url)


@require_POST
@rate_limit("donation", methods=("POST",))
def verify_donation_payment_view(request: HttpRequest) -> HttpResponse:
    """Verify Razorpay HMAC-SHA256 payment callback signature."""
    if request.content_type == "application/json":
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            payload = {}
        order_id = str(payload.get("razorpay_order_id", "")).strip()
        payment_id = str(payload.get("razorpay_payment_id", "")).strip()
        signature = str(payload.get("razorpay_signature", "")).strip()
    else:
        order_id = request.POST.get("razorpay_order_id", "").strip()
        payment_id = request.POST.get("razorpay_payment_id", "").strip()
        signature = request.POST.get("razorpay_signature", "").strip()

    verified, msg, donation = verify_razorpay_payment_signature(
        request=request,
        provider_order_id=order_id,
        provider_payment_id=payment_id,
        provider_signature=signature,
    )

    if not verified:
        if is_json_request(request):
            return JsonResponse(
                {"status": "error", "code": "verification_failed", "message": msg},
                status=400,
            )
        messages.error(request, msg)
        return redirect("donations:index")

    assert donation is not None
    receipt_url = reverse("donations:receipt", kwargs={"donation_id": donation.id})
    if is_json_request(request):
        return JsonResponse(
            {
                "status": "ok",
                "message": msg,
                "donation_id": str(donation.id),
                "receipt_url": receipt_url,
            }
        )
    messages.success(request, msg)
    return redirect(receipt_url)


@require_GET
def donation_receipt_view(request: HttpRequest, donation_id: str) -> HttpResponse:
    """Display the status and receipt summary for a Donation record."""
    donation = get_object_or_404(Donation, id=donation_id)
    return render(
        request,
        "donations/receipt.html",
        {
            "page_title": f"Donation Status [{donation.provider_order_id}] | InSave Hub",
            "donation": donation,
            "gateway_configured": is_razorpay_configured(),
            "razorpay_key_id": getattr(
                __import__("django.conf", fromlist=["settings"]).settings,
                "RAZORPAY_KEY_ID",
                "",
            ),
        },
    )
