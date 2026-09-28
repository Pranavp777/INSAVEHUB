"""Views and asynchronous API endpoints for Instagram Tools and the Download Interface."""
import json

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from apps.advertisements.services import _build_actor_filter, get_user_access_summary
from apps.core.rate_limit import rate_limit
from apps.core.utils import is_json_request
from apps.downloads.models import Download, Tool
from apps.downloads.services import (
    InstagramURLValidationError,
    analyze_instagram_url,
    authorize_and_complete_download,
    build_download_artifact_payload,
    ensure_default_tools,
)


def tools_list_view(request: HttpRequest) -> HttpResponse:
    """Render the dedicated Instagram Tools page with interactive glass modules."""
    ensure_default_tools()
    tools = Tool.objects.filter(is_active=True).order_by("display_order", "name")
    return render(
        request,
        "tools/index.html",
        {
            "page_title": "Instagram Content Utilities | InSave Hub",
            "meta_description": (
                "Explore precision glass modules for public Instagram Reels, Videos, "
                "Photography, Posts, Profile Media, and Technical Metadata."
            ),
            "tools": tools,
        },
    )


def tool_detail_view(request: HttpRequest, slug: str) -> HttpResponse:
    """Render an individual Instagram utility tool with embedded analyzer."""
    ensure_default_tools()
    tool = get_object_or_404(Tool, slug=slug, is_active=True)
    other_tools = Tool.objects.filter(is_active=True).exclude(pk=tool.pk).order_by("display_order")
    return render(
        request,
        "tools/tool_detail.html",
        {
            "page_title": f"{tool.name} | InSave Hub",
            "meta_description": tool.short_description,
            "tool": tool,
            "other_tools": other_tools,
        },
    )


def download_interface_view(request: HttpRequest) -> HttpResponse:
    """Render the central Instagram URL Download Interface and recent activity."""
    ensure_default_tools()
    tools = Tool.objects.filter(is_active=True).order_by("display_order")
    selected_tool_slug = request.GET.get("tool", "").strip()
    prefill_url = request.GET.get("url", "").strip()

    actor_q = _build_actor_filter(request)
    recent_downloads = (
        Download.objects.select_related("tool")
        .filter(actor_q)
        .order_by("-created_at")[:8]
    )

    return render(
        request,
        "downloads/interface.html",
        {
            "page_title": "Download Control Interface | InSave Hub",
            "meta_description": (
                "Analyze public Instagram URLs, inspect media specifications, and execute "
                "high-resolution downloads."
            ),
            "tools": tools,
            "selected_tool_slug": selected_tool_slug,
            "prefill_url": prefill_url,
            "recent_downloads": recent_downloads,
        },
    )


@require_POST
@rate_limit("analyze", methods=("POST",))
def analyze_url_api(request: HttpRequest) -> HttpResponse:
    """
    Asynchronous URL inspection endpoint.
    Validates public Instagram URLs and returns structured preview, format, and
    server-side access authorization metadata without exposing internal secrets.
    """
    if request.content_type == "application/json":
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            payload = {}
        raw_url = str(payload.get("url", "")).strip()
        tool_slug = str(payload.get("tool_slug", "")).strip() or None
    else:
        raw_url = request.POST.get("url", "").strip()
        tool_slug = request.POST.get("tool_slug", "").strip() or None

    try:
        download, access_summary = analyze_instagram_url(
            request=request,
            raw_url=raw_url,
            tool_slug=tool_slug,
        )
    except InstagramURLValidationError as exc:
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
        return redirect("downloads:interface")

    execute_url = reverse("downloads:execute", kwargs={"token": download.download_token})
    ad_gate_url = f"{reverse('advertisements:gate')}?download_id={download.id}"

    response_data = {
        "status": "ok",
        "download": {
            "id": str(download.id),
            "shortcode": download.shortcode,
            "source_url": download.source_url,
            "media_title": download.media_title,
            "author_handle": download.author_handle,
            "content_type": download.content_type,
            "content_type_label": download.get_content_type_display(),
            "media_format": download.media_format,
            "resolution": download.resolution,
            "file_size_label": download.file_size_label,
            "file_size_bytes": download.file_size_bytes,
            "tool_name": download.tool.name if download.tool else "Instagram Utility",
            "preview_metadata": download.preview_metadata,
            "status": download.status,
            "execute_url": execute_url,
            "ad_gate_url": ad_gate_url,
        },
        "access": {
            "mode": access_summary["mode"],
            "label": access_summary["label"],
            "ad_required": access_summary["ad_required"],
            "has_free_24h": access_summary["has_free_24h"],
            "free_24h_formatted": access_summary["free_24h_formatted"],
            "free_24h_remaining_seconds": access_summary["free_24h_remaining_seconds"],
        },
    }

    if is_json_request(request):
        return JsonResponse(response_data)

    return redirect("downloads:interface")


@require_http_methods(["GET", "POST"])
@rate_limit("download", methods=("GET", "POST"))
def execute_download_view(request: HttpRequest, token: str) -> HttpResponse:
    """
    Server-validated media download endpoint.
    Enforces the 30-second advertisement requirement after the first completed download
    unless an active 24-hour FreeAccessSession is verified on the server.
    """
    authorized, download, ad_session, message = authorize_and_complete_download(
        request=request,
        download_token=token,
    )

    if not authorized:
        if download is not None and ad_session is not None:
            ad_gate_url = f"{reverse('advertisements:gate')}?download_id={download.id}"
            if is_json_request(request):
                return JsonResponse(
                    {
                        "status": "ad_required",
                        "code": "advertisement_required",
                        "message": "Your next download will be available after the advertisement.",
                        "ad_gate_url": ad_gate_url,
                        "ad_session_id": str(ad_session.id),
                        "remaining_seconds": ad_session.remaining_seconds,
                    },
                    status=403,
                )
            return redirect(ad_gate_url)

        if is_json_request(request):
            return JsonResponse(
                {
                    "status": "error",
                    "code": "unauthorized_download",
                    "message": message,
                },
                status=403,
            )
        return render(
            request,
            "errors/403.html",
            {
                "error_code": "403",
                "error_title": "Download Authorization Denied",
                "error_message": message,
            },
            status=403,
        )

    assert download is not None
    if is_json_request(request) and request.GET.get("Check") == "1":
        access_summary = get_user_access_summary(request)
        return JsonResponse(
            {
                "status": "ok",
                "message": "Download completed.",
                "download_id": str(download.id),
                "access": access_summary,
            }
        )

    payload_bytes, mime_type, filename = build_download_artifact_payload(download)
    response = HttpResponse(payload_bytes, content_type=mime_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Content-Length"] = str(len(payload_bytes))
    return response


def download_history_view(request: HttpRequest) -> HttpResponse:
    """Render the user's or session's download history table."""
    actor_q = _build_actor_filter(request)
    downloads = (
        Download.objects.select_related("tool")
        .filter(actor_q)
        .order_by("-created_at")[:50]
    )
    return render(
        request,
        "downloads/history.html",
        {
            "page_title": "Download History | InSave Hub",
            "meta_description": "Review your analyzed Instagram content and completed media downloads.",
            "downloads": downloads,
        },
    )
