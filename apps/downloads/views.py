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


def _serialize_download_dict(download: Download) -> dict:
    """Serialize a Download model instance for frontend result rendering and auto-download."""
    execute_url = reverse("downloads:execute", kwargs={"token": download.download_token})
    preview_url = f"{execute_url}?preview=1"
    ad_gate_url = f"{reverse('advertisements:gate')}?download_id={download.id}&mode=30s"
    initial_ad_gate_url = f"{reverse('advertisements:gate')}?download_id={download.id}&mode=5s"

    meta = download.preview_metadata if isinstance(download.preview_metadata, dict) else {}
    raw_dur = float(meta.get("duration_seconds") or 0)
    if raw_dur > 0:
        mins = int(raw_dur // 60)
        secs = int(round(raw_dur % 60))
        duration_label = f"{mins:02d}:{secs:02d} ({raw_dur:.1f}s)"
    elif download.content_type in (Download.ContentType.VIDEO, Download.ContentType.REEL):
        duration_label = "00:15 (HD Stream)"
    else:
        duration_label = "Static Image"

    return {
        "id": str(download.id),
        "shortcode": download.shortcode,
        "source_url": download.source_url,
        "media_title": download.media_title,
        "author_handle": download.author_handle,
        "content_type": download.content_type,
        "content_type_label": download.get_content_type_display(),
        "media_format": download.media_format,
        "resolution": download.resolution,
        "duration_label": duration_label,
        "file_size_label": download.file_size_label,
        "file_size_bytes": download.file_size_bytes,
        "tool_name": download.tool.name if download.tool else "Instagram Utility",
        "preview_metadata": meta,
        "status": download.status,
        "execute_url": execute_url,
        "preview_url": preview_url,
        "ad_gate_url": ad_gate_url,
        "initial_ad_gate_url": initial_ad_gate_url,
    }


def tools_list_view(request: HttpRequest) -> HttpResponse:
    """Render the dedicated Instagram Tools page with interactive glass modules."""
    ensure_default_tools()
    tools = Tool.objects.filter(is_active=True).order_by("display_order", "name")
    return render(
        request,
        "tools/index.html",
        {
            "page_title": "Instagram Video, Reel, Photo & Post Downloader Tools | INSTASAVE HUB",
            "meta_description": (
                "Free Instagram Downloader tools to preview and save Instagram Reels, Videos, "
                "Photos, Carousels, and HD Profile Pictures in 1080p MP4 & JPG."
            ),
            "meta_keywords": (
                "instagram tools, instagram reel downloader, instagram video downloader, "
                "instagram photo downloader, instagram post downloader, ig profile picture viewer"
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
            "page_title": f"{tool.name} — Free 1080p HD Preview & Download | INSTASAVE HUB",
            "meta_description": f"{tool.short_description} Live video preview and fast 1080p download on INSTASAVE HUB.",
            "meta_keywords": f"{tool.name.lower()}, {tool.slug.replace('-', ' ')}, instagram downloader, save instagram 1080p, instasave hub",
            "tool": tool,
            "other_tools": other_tools,
        },
    )


def download_interface_view(request: HttpRequest) -> HttpResponse:
    """Render the central Instagram URL Download Interface, active download result, and recent activity."""
    ensure_default_tools()
    tools = Tool.objects.filter(is_active=True).order_by("display_order")
    selected_tool_slug = request.GET.get("tool", "").strip()
    prefill_url = request.GET.get("url", "").strip()
    download_id = request.GET.get("download_id", "").strip()
    auto_download = request.GET.get("auto_download") == "1"

    actor_q = _build_actor_filter(request)
    active_download_json = ""
    if download_id:
        try:
            active_dl = (
                Download.objects.select_related("tool")
                .filter(actor_q, id=download_id)
                .first()
            )
            if active_dl:
                if not prefill_url:
                    prefill_url = active_dl.source_url
                access_summary = get_user_access_summary(request)
                active_download_json = json.dumps(
                    {
                        "download": _serialize_download_dict(active_dl),
                        "access": {
                            "state": access_summary["state"],
                            "mode": access_summary["mode"],
                            "label": access_summary["label"],
                            "sublabel": access_summary["sublabel"],
                            "ad_required": access_summary["ad_required"],
                            "initial_5s_ad_required": False if auto_download else access_summary["initial_5s_ad_required"],
                            "first_download_completed": access_summary["first_download_completed"],
                            "has_free_24h": access_summary["has_free_24h"],
                            "free_24h_formatted": access_summary["free_24h_formatted"],
                            "free_24h_remaining_seconds": access_summary["free_24h_remaining_seconds"],
                        },
                        "auto_download": auto_download,
                    }
                )
        except ValueError:
            pass

    recent_downloads = (
        Download.objects.select_related("tool")
        .filter(actor_q)
        .order_by("-created_at")[:8]
    )

    return render(
        request,
        "downloads/interface.html",
        {
            "page_title": "Instagram Video & Reel Downloader with Live Preview | INSTASAVE HUB",
            "meta_description": (
                "Paste any public Instagram URL to preview videos in 1080p HD and download "
                "Instagram Reels, Videos, Photos, and Carousels instantly."
            ),
            "meta_keywords": (
                "instagram downloader, instagram video preview, download instagram reel mp4, "
                "save instagram post hd, instasave hub"
            ),
            "tools": tools,
            "selected_tool_slug": selected_tool_slug,
            "prefill_url": prefill_url,
            "active_download_json": active_download_json,
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

    response_data = {
        "status": "ok",
        "download": _serialize_download_dict(download),
        "access": {
            "state": access_summary["state"],
            "mode": access_summary["mode"],
            "label": access_summary["label"],
            "sublabel": access_summary["sublabel"],
            "ad_required": access_summary["ad_required"],
            "initial_5s_ad_required": access_summary["initial_5s_ad_required"],
            "first_download_completed": access_summary["first_download_completed"],
            "has_free_24h": access_summary["has_free_24h"],
            "free_24h_formatted": access_summary["free_24h_formatted"],
            "free_24h_remaining_seconds": access_summary["free_24h_remaining_seconds"],
        },
    }

    if is_json_request(request):
        return JsonResponse(response_data)

    return redirect(f"{reverse('downloads:interface')}?download_id={download.id}")


@require_http_methods(["GET", "POST"])
@rate_limit("download", methods=("GET", "POST"))
def execute_download_view(request: HttpRequest, token: str) -> HttpResponse:
    """
    Server-validated media download endpoint.
    Supports inline preview streaming when ?preview=1 is passed, and enforces the
    30-second advertisement requirement for full downloads after the first completed download.
    """
    if request.GET.get("preview") == "1":
        actor_q = _build_actor_filter(request)
        preview_download = (
            Download.objects.select_related("tool")
            .filter(actor_q, download_token=token)
            .first()
            or Download.objects.select_related("tool").filter(download_token=token).first()
        )
        if preview_download is None:
            return HttpResponse("Preview token not found.", status=404)
        payload_bytes, mime_type, filename = build_download_artifact_payload(preview_download)
        response = HttpResponse(payload_bytes, content_type=mime_type)
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        response["Content-Length"] = str(len(payload_bytes))
        response["Accept-Ranges"] = "bytes"
        return response

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
            "page_title": "Download History | INSTASAVE HUB",
            "meta_description": "Review your analyzed Instagram content and completed media downloads.",
            "downloads": downloads,
        },
    )
