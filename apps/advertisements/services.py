"""
Server-side access control and advertisement countdown validation services.
Enforces the 1st-download-free -> 30-second server-validated ad -> 24-hour free access lifecycle.
"""
import secrets
from datetime import timedelta
from typing import Any, Dict, Optional, Tuple

from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest
from django.utils import timezone

from apps.advertisements.models import AdSession, FreeAccessSession
from apps.core.models import AuditLog, SiteConfiguration
from apps.core.utils import ensure_session_key, get_ip_hash


def _build_actor_filter(request: HttpRequest) -> Q:
    """Build a query filter matching either the authenticated user or the server session."""
    session_key = ensure_session_key(request)
    if hasattr(request, "user") and request.user.is_authenticated:
        return Q(user=request.user) | Q(session_key=session_key)
    return Q(session_key=session_key)


def expire_stale_sessions(request: Optional[HttpRequest] = None) -> None:
    """Deactivate any FreeAccessSession whose `expires_at` timestamp has passed."""
    now = timezone.now()
    qs = FreeAccessSession.objects.filter(is_active=True, expires_at__lte=now)
    if request is not None:
        qs = qs.filter(_build_actor_filter(request))
    qs.update(is_active=False)


def get_active_free_access_session(request: HttpRequest) -> Optional[FreeAccessSession]:
    """Return the active, non-expired 24-hour FreeAccessSession for the current user/session."""
    expire_stale_sessions(request)
    now = timezone.now()
    actor_q = _build_actor_filter(request)
    session = (
        FreeAccessSession.objects.filter(actor_q, is_active=True, expires_at__gt=now)
        .order_by("-expires_at")
        .first()
    )
    if session and hasattr(request, "user") and request.user.is_authenticated and session.user is None:
        session.user = request.user
        session.save(update_fields=["user"])
    return session


def get_completed_downloads_in_current_cycle(request: HttpRequest) -> int:
    """
    Count completed initial-allowance downloads for this user/session since their
    most recent expired 24-hour FreeAccessSession (or all time if none).
    Downloads executed under a 24-hour FreeAccessSession pass do not consume the
    next cycle's initial download allowance.
    """
    from apps.downloads.models import Download

    actor_q = _build_actor_filter(request)
    last_expired_pass = (
        FreeAccessSession.objects.filter(actor_q, expires_at__lte=timezone.now())
        .order_by("-started_at")
        .first()
    )
    downloads_qs = Download.objects.filter(
        actor_q,
        status=Download.Status.COMPLETED,
        access_mode=Download.AccessMode.INITIAL_FREE,
    )
    if last_expired_pass is not None:
        cutoff = max(last_expired_pass.started_at, last_expired_pass.expires_at)
        downloads_qs = downloads_qs.filter(completed_at__gt=cutoff)
    return downloads_qs.count()


def get_active_ad_session(request: HttpRequest) -> Optional[AdSession]:
    """Retrieve an existing active AdSession for the current user/session."""
    actor_q = _build_actor_filter(request)
    cutoff = timezone.now() - timedelta(minutes=30)
    return (
        AdSession.objects.filter(
            actor_q,
            status=AdSession.Status.ACTIVE,
            started_at__gte=cutoff,
        )
        .order_by("-started_at")
        .first()
    )


def get_or_create_active_ad_session(
    request: HttpRequest,
    pending_download: Any = None,
) -> AdSession:
    """
    Retrieve an existing active AdSession or initialize a new 30-second countdown.
    Refreshing the browser reuses the existing AdSession so the timer cannot be
    bypassed or manipulated from the client.
    """
    existing = get_active_ad_session(request)
    if existing is not None:
        if pending_download is not None and existing.pending_download_id != pending_download.id:
            existing.pending_download = pending_download
            existing.save(update_fields=["pending_download"])
        return existing

    config = SiteConfiguration.get_solo()
    duration = config.ad_countdown_seconds
    now = timezone.now()
    session_key = ensure_session_key(request)
    ip_hash = get_ip_hash(request)
    user = request.user if (hasattr(request, "user") and request.user.is_authenticated) else None

    ad_session = AdSession.objects.create(
        user=user,
        session_key=session_key,
        ip_hash=ip_hash,
        pending_download=pending_download,
        required_duration_seconds=duration,
        started_at=now,
        eligible_at=now + timedelta(seconds=duration),
        status=AdSession.Status.ACTIVE,
    )
    AuditLog.record(
        event_type="ad.session_started",
        description=f"Started {duration}s advertisement countdown session.",
        request=request,
        resource_type="AdSession",
        resource_id=str(ad_session.id),
    )
    return ad_session


def get_user_access_summary(request: HttpRequest) -> Dict[str, Any]:
    """
    Compute the complete server-side access state for the current user/session.
    Returns whether a 24-hour free pass is active, whether the initial download is available,
    or whether the 30-second advertisement requirement is active.
    """
    config = SiteConfiguration.get_solo()
    free_session = get_active_free_access_session(request)

    if free_session is not None:
        return {
            "mode": "free_24h_pass",
            "label": "24-Hour Free Access Active",
            "has_free_24h": True,
            "free_24h_expires_at": free_session.expires_at,
            "free_24h_remaining_seconds": free_session.remaining_seconds,
            "free_24h_formatted": free_session.formatted_remaining,
            "ad_required": False,
            "can_download_immediately": True,
            "completed_in_cycle": get_completed_downloads_in_current_cycle(request),
            "free_allowance": config.free_downloads_before_ad,
            "active_ad_session_id": None,
        }

    completed_in_cycle = get_completed_downloads_in_current_cycle(request)
    ad_required = bool(
        config.enable_advertisements and completed_in_cycle >= config.free_downloads_before_ad
    )
    active_ad = get_active_ad_session(request) if ad_required else None

    return {
        "mode": "ad_required" if ad_required else "initial_free",
        "label": "Advertisement Verification Required" if ad_required else "Free Access Available",
        "has_free_24h": False,
        "free_24h_expires_at": None,
        "free_24h_remaining_seconds": 0,
        "free_24h_formatted": "00:00:00",
        "ad_required": ad_required,
        "can_download_immediately": not ad_required,
        "completed_in_cycle": completed_in_cycle,
        "free_allowance": config.free_downloads_before_ad,
        "active_ad_session_id": str(active_ad.id) if active_ad else None,
        "active_ad_remaining_seconds": active_ad.remaining_seconds if active_ad else config.ad_countdown_seconds,
    }


@transaction.atomic
def complete_ad_session_and_grant_free_access(
    request: HttpRequest,
    ad_session_id: str,
    nonce_token: str,
) -> Tuple[bool, str, Optional[FreeAccessSession], Optional[AdSession]]:
    """
    Validate on the server that:
    1. The AdSession belongs to the current user/session
    2. The cryptographic `nonce_token` matches
    3. The server clock `timezone.now()` is >= `ad_session.eligible_at` (full 30 seconds elapsed)
    Upon validation, marks the AdSession completed and issues a 24-hour FreeAccessSession.
    """
    actor_q = _build_actor_filter(request)
    try:
        ad_session = AdSession.objects.select_for_update().get(actor_q, id=ad_session_id)
    except (AdSession.DoesNotExist, ValueError):
        AuditLog.record(
            event_type="ad.invalid_session_attempt",
            description="Attempted to complete non-existent or unauthorized AdSession.",
            request=request,
            severity=AuditLog.Severity.WARNING,
        )
        return False, "Advertisement session not found or does not belong to your session.", None, None

    if not nonce_token or not secrets.compare_digest(ad_session.nonce_token, str(nonce_token)):
        AuditLog.record(
            event_type="ad.invalid_nonce",
            description="AdSession completion rejected due to invalid security nonce.",
            request=request,
            severity=AuditLog.Severity.WARNING,
            resource_type="AdSession",
            resource_id=str(ad_session.id),
        )
        return False, "Invalid security verification token for this advertisement session.", None, ad_session

    if ad_session.status == AdSession.Status.COMPLETED:
        existing_free = getattr(ad_session, "granted_free_session", None)
        return True, "Advertisement requirement already completed.", existing_free, ad_session

    if ad_session.status != AdSession.Status.ACTIVE:
        return False, "This advertisement session has expired. Please start a new session.", None, ad_session

    now = timezone.now()
    if now < ad_session.eligible_at:
        remaining = ad_session.remaining_seconds
        AuditLog.record(
            event_type="ad.premature_completion_blocked",
            description=f"Blocked premature ad completion with {remaining}s remaining on server clock.",
            request=request,
            severity=AuditLog.Severity.WARNING,
            resource_type="AdSession",
            resource_id=str(ad_session.id),
            metadata={"remaining_seconds": remaining},
        )
        return (
            False,
            f"Your next download will be available after the advertisement. ({remaining}s remaining)",
            None,
            ad_session,
        )

    config = SiteConfiguration.get_solo()
    ad_session.status = AdSession.Status.COMPLETED
    ad_session.completed_at = now
    ad_session.save(update_fields=["status", "completed_at"])

    session_key = ensure_session_key(request)
    ip_hash = get_ip_hash(request)
    user = request.user if (hasattr(request, "user") and request.user.is_authenticated) else ad_session.user

    # Deactivate any prior active sessions before issuing the fresh 24-hour window
    FreeAccessSession.objects.filter(actor_q, is_active=True).update(is_active=False)

    free_session = FreeAccessSession.objects.create(
        user=user,
        session_key=session_key,
        ip_hash=ip_hash,
        source_ad_session=ad_session,
        started_at=now,
        expires_at=now + timedelta(hours=config.free_access_hours),
        is_active=True,
    )

    AuditLog.record(
        event_type="ad.completed_free_access_granted",
        description=(
            f"Completed 30s advertisement and unlocked {config.free_access_hours}-hour free access "
            f"until {free_session.expires_at.isoformat()}."
        ),
        request=request,
        resource_type="FreeAccessSession",
        resource_id=str(free_session.id),
    )

    return (
        True,
        f"Advertisement completed. Your {config.free_access_hours}-hour free access pass is now active.",
        free_session,
        ad_session,
    )
