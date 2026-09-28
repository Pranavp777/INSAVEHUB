"""Security and request utility helpers for InSave Hub."""
import hashlib
from typing import Optional

from django.conf import settings
from django.http import HttpRequest


def get_client_ip(request: HttpRequest) -> str:
    """
    Extract client IP safely with Cloudflare (`CF-Connecting-IP`) and reverse-proxy support.
    """
    cf_ip = request.META.get("HTTP_CF_CONNECTING_IP")
    if cf_ip:
        return cf_ip.strip()

    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()

    return request.META.get("REMOTE_ADDR", "127.0.0.1") or "127.0.0.1"


def get_ip_hash(request: HttpRequest) -> str:
    """
    Create a privacy-preserving salted SHA-256 hash of the client IP address.
    Avoids storing raw personal IP addresses in the database.
    """
    raw_ip = get_client_ip(request)
    salt = settings.SECRET_KEY[:24]
    digest = hashlib.sha256(f"{salt}:{raw_ip}".encode("utf-8")).hexdigest()
    return digest


def ensure_session_key(request: HttpRequest) -> str:
    """Ensure the current request has a persisted server-side session key."""
    if not request.session.session_key:
        request.session.save()
    return request.session.session_key or "anonymous-session"


def is_json_request(request: HttpRequest) -> bool:
    """Determine if the incoming request expects a JSON response."""
    accept = request.headers.get("Accept", "")
    content_type = request.headers.get("Content-Type", "")
    requested_with = request.headers.get("X-Requested-With", "")
    return (
        "application/json" in accept
        or "application/json" in content_type
        or requested_with == "XMLHttpRequest"
        or request.path.startswith("/api/")
    )
