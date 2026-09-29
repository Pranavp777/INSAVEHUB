"""Views for the User Glass Control Center and Custom Admin Analytics Dashboard."""
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.accounts.models import get_or_create_user_profile
from apps.advertisements.models import AdSession, FreeAccessSession
from apps.advertisements.services import (
    _build_actor_filter,
    expire_stale_sessions,
    get_user_access_summary,
)
from apps.core.models import AuditLog, SiteConfiguration
from apps.donations.models import Donation
from apps.downloads.models import Download, DownloadAttempt, Tool
from apps.downloads.services import ensure_default_tools

User = get_user_model()


@login_required
def dashboard_index_view(request: HttpRequest) -> HttpResponse:
    """Render the User Dashboard Glass Control Center."""
    ensure_default_tools()
    profile = get_or_create_user_profile(request.user)
    config = SiteConfiguration.get_solo()
    access_summary = get_user_access_summary(request)

    actor_q = _build_actor_filter(request)
    downloads_qs = Download.objects.select_related("tool").filter(actor_q)
    recent_downloads = downloads_qs.order_by("-created_at")[:12]

    total_downloads = downloads_qs.count()
    completed_downloads = downloads_qs.filter(status=Download.Status.COMPLETED).count()
    ad_completed_count = AdSession.objects.filter(
        actor_q, status=AdSession.Status.COMPLETED
    ).count()

    tools = Tool.objects.filter(is_active=True).order_by("display_order")
    user_donations = Donation.objects.filter(user=request.user).order_by("-created_at")[:5]

    return render(
        request,
        "dashboard/index.html",
        {
            "page_title": "Control Center Dashboard | INSTASAVE HUB",
            "meta_description": "Manage your Instagram utilities, 24-hour free access pass, and download history.",
            "profile": profile,
            "tools": tools,
            "recent_downloads": recent_downloads,
            "total_downloads": total_downloads,
            "completed_downloads": completed_downloads,
            "ad_completed_count": ad_completed_count,
            "access_summary": access_summary,
            "preset_amounts": config.get_preset_amounts_list(),
            "user_donations": user_donations,
        },
    )


@login_required
def admin_analytics_view(request: HttpRequest) -> HttpResponse:
    """
    Custom Admin Analytics and Platform Operations Dashboard.
    Strictly enforces staff/admin authorization (`is_staff` or `is_superuser`).
    """
    if not (request.user.is_staff or request.user.is_superuser):
        AuditLog.record(
            event_type="admin.unauthorized_access",
            description="Non-staff user attempted to access the Admin Analytics Dashboard.",
            request=request,
            user=request.user,
            severity=AuditLog.Severity.WARNING,
        )
        return render(
            request,
            "errors/403.html",
            {
                "error_code": "403",
                "error_title": "Administrative Clearance Required",
                "error_message": "This control surface is restricted to authorized platform administrators.",
            },
            status=403,
        )

    ensure_default_tools()
    expire_stale_sessions()
    config = SiteConfiguration.get_solo()

    if request.method == "POST":
        action = request.POST.get("admin_action", "")
        if action == "toggle_tool":
            tool_id = request.POST.get("tool_id")
            tool = Tool.objects.filter(pk=tool_id).first()
            if tool:
                tool.is_active = not tool.is_active
                tool.save(update_fields=["is_active", "updated_at"])
                AuditLog.record(
                    event_type="admin.tool_toggled",
                    description=f"Administrator toggled tool '{tool.name}' active={tool.is_active}.",
                    request=request,
                    user=request.user,
                )
                messages.success(request, f"Updated tool '{tool.name}' status.")
        elif action == "update_access_rules":
            try:
                countdown = max(5, min(300, int(request.POST.get("ad_countdown_seconds", 30))))
                free_hours = max(1, min(168, int(request.POST.get("free_access_hours", 24))))
                config.ad_countdown_seconds = countdown
                config.free_access_hours = free_hours
                config.enable_advertisements = request.POST.get("enable_advertisements") == "on"
                config.enable_donations = request.POST.get("enable_donations") == "on"
                config.save()
                AuditLog.record(
                    event_type="admin.config_updated",
                    description=f"Updated platform rules: ad={countdown}s, free_access={free_hours}h.",
                    request=request,
                    user=request.user,
                )
                messages.success(request, "Platform access and advertisement parameters updated.")
            except ValueError:
                messages.error(request, "Invalid numeric configuration values.")
        return redirect("dashboard:admin_analytics")

    now = timezone.now()
    total_users = User.objects.count()
    active_users = User.objects.filter(is_active=True).count()

    total_downloads = Download.objects.count()
    successful_downloads = Download.objects.filter(status=Download.Status.COMPLETED).count()
    failed_downloads = DownloadAttempt.objects.filter(
        Q(status=DownloadAttempt.AttemptStatus.INVALID_URL)
        | Q(status=DownloadAttempt.AttemptStatus.RESTRICTED_CONTENT)
        | Q(status=DownloadAttempt.AttemptStatus.BLOCKED_RATE_LIMIT)
    ).count()

    ad_completions = AdSession.objects.filter(status=AdSession.Status.COMPLETED).count()
    active_24h_sessions = FreeAccessSession.objects.filter(
        is_active=True, expires_at__gt=now
    ).count()

    total_donations_count = Donation.objects.count()
    completed_donations_qs = Donation.objects.filter(status=Donation.Status.COMPLETED)
    completed_donations_count = completed_donations_qs.count()
    donation_revenue_total = (
        completed_donations_qs.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    )

    popular_tools = Tool.objects.all().order_by("-total_uses", "display_order")
    recent_audit_logs = AuditLog.objects.select_related("user").order_by("-created_at")[:15]
    recent_attempts = DownloadAttempt.objects.select_related("user", "tool").order_by("-created_at")[:12]

    return render(
        request,
        "dashboard/admin_analytics.html",
        {
            "page_title": "Admin Telemetry & Operations | INSTASAVE HUB",
            "total_users": total_users,
            "active_users": active_users,
            "total_downloads": total_downloads,
            "successful_downloads": successful_downloads,
            "failed_downloads": failed_downloads,
            "ad_completions": ad_completions,
            "active_24h_sessions": active_24h_sessions,
            "total_donations_count": total_donations_count,
            "completed_donations_count": completed_donations_count,
            "donation_revenue_total": donation_revenue_total,
            "popular_tools": popular_tools,
            "recent_audit_logs": recent_audit_logs,
            "recent_attempts": recent_attempts,
        },
    )
