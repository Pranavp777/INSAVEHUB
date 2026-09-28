"""
Configurable server-side rate limiter for InSave Hub.
Applies limits to URL analysis, downloads, authentication, password resets,
OAuth callbacks, and donation requests.
"""
from functools import wraps
from typing import Callable, Optional, Tuple

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render

from apps.core.models import AuditLog, SiteConfiguration
from apps.core.utils import get_ip_hash, is_json_request

SCOPE_MESSAGES = {
    "analyze": "You have reached the maximum number of URL inspections per minute. Please wait briefly before analyzing another link.",
    "download": "Download request rate limit reached. Please pause for a moment before initiating another media transfer.",
    "auth": "Too many authentication attempts detected from your connection. Please wait a minute before trying again.",
    "password_reset": "Password recovery request limit reached for this hour. Please check your inbox or wait before requesting another link.",
    "oauth": "Too many OAuth verification requests in a short window. Please wait a moment and retry signing in.",
    "donation": "Too many payment initialization requests. Please wait briefly before creating another contribution order.",
}


def get_limit_for_scope(scope: str) -> Tuple[int, int]:
    """
    Return (max_requests, window_seconds) for the requested rate-limit scope.
    Reads dynamically from SiteConfiguration with fallback to settings.RATE_LIMITS.
    """
    config = SiteConfiguration.get_solo()
    mapping = {
        "analyze": (config.rate_limit_analyze_per_min, 60),
        "download": (config.rate_limit_download_per_min, 60),
        "auth": (config.rate_limit_auth_per_min, 60),
        "password_reset": (config.rate_limit_password_reset_per_hour, 3600),
        "oauth": (config.rate_limit_oauth_per_min, 60),
        "donation": (config.rate_limit_donation_per_min, 60),
    }
    if scope in mapping:
        return mapping[scope]
    default_limit = settings.RATE_LIMITS.get(scope, 15)
    return (default_limit, 60)


def check_rate_limit(
    request: HttpRequest,
    scope: str,
    custom_limit: Optional[int] = None,
    custom_window: Optional[int] = None,
) -> Tuple[bool, int, int]:
    """
    Increment and check the rate limit counter for a request and scope.
    Returns (is_allowed, current_count, retry_after_seconds).
    """
    max_requests, window_seconds = get_limit_for_scope(scope)
    if custom_limit is not None:
        max_requests = custom_limit
    if custom_window is not None:
        window_seconds = custom_window

    ip_hash = get_ip_hash(request)
    user_part = f"u:{request.user.pk}" if (hasattr(request, "user") and request.user.is_authenticated) else "anon"
    cache_key = f"rl:{scope}:{ip_hash}:{user_part}"

    current = cache.get(cache_key)
    if current is None:
        cache.set(cache_key, 1, timeout=window_seconds)
        return True, 1, window_seconds

    if int(current) >= max_requests:
        AuditLog.record(
            event_type=f"rate_limit.{scope}",
            description=f"Rate limit exceeded for scope '{scope}' ({current}/{max_requests}).",
            request=request,
            severity=AuditLog.Severity.WARNING,
            metadata={"scope": scope, "limit": max_requests, "window": window_seconds},
        )
        return False, int(current), window_seconds

    try:
        new_val = cache.incr(cache_key)
    except ValueError:
        new_val = int(current) + 1
        cache.set(cache_key, new_val, timeout=window_seconds)

    return True, int(new_val), window_seconds


def rate_limit_response(request: HttpRequest, scope: str, retry_after: int = 60) -> HttpResponse:
    """Build a friendly 429 Too Many Requests response in JSON or HTML."""
    friendly_message = SCOPE_MESSAGES.get(
        scope,
        "Request rate limit exceeded. Please wait a moment before trying again.",
    )
    if is_json_request(request):
        response = JsonResponse(
            {
                "status": "error",
                "code": "rate_limit_exceeded",
                "scope": scope,
                "message": friendly_message,
                "retry_after_seconds": retry_after,
            },
            status=429,
        )
    else:
        response = render(
            request,
            "errors/429.html",
            {
                "error_title": "Request Rate Limit Reached",
                "error_message": friendly_message,
                "retry_after_seconds": retry_after,
                "scope": scope,
            },
            status=429,
        )
    response["Retry-After"] = str(retry_after)
    return response


def rate_limit(
    scope: str,
    methods: Tuple[str, ...] = ("POST", "GET"),
    custom_limit: Optional[int] = None,
    custom_window: Optional[int] = None,
) -> Callable:
    """Decorator to enforce configurable server-side rate limiting on Django views."""

    def decorator(view_func: Callable) -> Callable:
        @wraps(view_func)
        def _wrapped_view(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            if request.method in methods:
                allowed, _count, retry_after = check_rate_limit(
                    request,
                    scope=scope,
                    custom_limit=custom_limit,
                    custom_window=custom_window,
                )
                if not allowed:
                    return rate_limit_response(request, scope=scope, retry_after=retry_after)
            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator
