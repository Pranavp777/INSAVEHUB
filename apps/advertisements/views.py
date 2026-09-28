"""Views and API endpoints for the 30-second advertisement gate and 24-hour free access unlock."""
import json

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from apps.advertisements.models import AdSession
from apps.advertisements.services import (
    _build_actor_filter,
    complete_ad_session_and_grant_free_access,
    get_active_free_access_session,
    get_or_create_active_ad_session,
)
from apps.core.utils import is_json_request


@require_GET
def ad_gate_view(request: HttpRequest) -> HttpResponse:
    """
    Render the 30-second server-validated advertisement interstitial screen.
    Displays: "Your next download will be available after the advertisement."
    Refreshing the page preserves the existing server-side countdown.
    """
    from apps.downloads.models import Download

    pending_download = None
    download_id = request.GET.get("download_id", "").strip()
    if download_id:
        actor_q = _build_actor_filter(request)
        try:
            pending_download = Download.objects.filter(actor_q, id=download_id).first()
        except ValueError:
            pending_download = None

    free_session = get_active_free_access_session(request)
    if free_session is not None:
        if pending_download is not None:
            return redirect(
                reverse("downloads:execute", kwargs={"token": pending_download.download_token})
            )
        return redirect("downloads:interface")

    ad_session = get_or_create_active_ad_session(request, pending_download=pending_download)

    return render(
        request,
        "downloads/ad_gate.html",
        {
            "page_title": "Advertisement Verification | InSave Hub",
            "meta_description": "Complete the 30-second sponsor interval to unlock 24-hour free access.",
            "ad_session": ad_session,
            "pending_download": ad_session.pending_download,
            "remaining_seconds": ad_session.remaining_seconds,
            "total_duration_seconds": ad_session.required_duration_seconds,
        },
    )


@require_GET
def ad_status_api(request: HttpRequest, session_id: str) -> JsonResponse:
    """Return authoritative server-side remaining seconds for an active AdSession."""
    actor_q = _build_actor_filter(request)
    try:
        ad_session = AdSession.objects.get(actor_q, id=session_id)
    except (AdSession.DoesNotExist, ValueError):
        return JsonResponse(
            {"status": "error", "message": "Advertisement session not found."},
            status=404,
        )

    return JsonResponse(
        {
            "status": "ok",
            "ad_session_id": str(ad_session.id),
            "session_status": ad_session.status,
            "remaining_seconds": ad_session.remaining_seconds,
            "required_duration_seconds": ad_session.required_duration_seconds,
            "is_ready_to_complete": ad_session.is_ready_to_complete,
        }
    )


@require_POST
def ad_complete_view(request: HttpRequest) -> HttpResponse:
    """
    Validate and complete the 30-second advertisement session on the server.
    Rejects premature attempts with HTTP 403.
    Upon completion, issues a 24-hour FreeAccessSession and unlocks the next download.
    """
    if request.content_type == "application/json":
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            payload = {}
        ad_session_id = str(payload.get("ad_session_id", "")).strip()
        nonce_token = str(payload.get("nonce_token", "")).strip()
    else:
        ad_session_id = request.POST.get("ad_session_id", "").strip()
        nonce_token = request.POST.get("nonce_token", "").strip()

    success, message, free_session, ad_session = complete_ad_session_and_grant_free_access(
        request=request,
        ad_session_id=ad_session_id,
        nonce_token=nonce_token,
    )

    if not success:
        remaining = ad_session.remaining_seconds if ad_session else 30
        if is_json_request(request):
            return JsonResponse(
                {
                    "status": "error",
                    "code": "ad_countdown_incomplete",
                    "message": message,
                    "remaining_seconds": remaining,
                },
                status=403,
            )
        messages.error(request, message)
        return redirect("advertisements:gate")

    next_url = reverse("downloads:interface")
    download_execute_url = None
    if ad_session and ad_session.pending_download:
        download_execute_url = reverse(
            "downloads:execute",
            kwargs={"token": ad_session.pending_download.download_token},
        )
        next_url = download_execute_url

    if is_json_request(request):
        return JsonResponse(
            {
                "status": "ok",
                "message": message,
                "free_access_granted": True,
                "free_access_expires_at": free_session.expires_at.isoformat() if free_session else None,
                "free_access_remaining_seconds": free_session.remaining_seconds if free_session else 0,
                "free_access_formatted": free_session.formatted_remaining if free_session else "24:00:00",
                "redirect_url": next_url,
                "download_execute_url": download_execute_url,
            }
        )

    messages.success(request, message)
    return redirect(next_url)
