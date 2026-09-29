"""Security headers and platform maintenance middleware."""
from typing import Callable

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from apps.core.models import SiteConfiguration


class SecurityHeadersMiddleware:
    """
    Injects production security headers on all HTTP responses.
    Ensures advertisement timers and download tokens are never cached by browsers.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)

        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' https://checkout.razorpay.com https://www.googletagmanager.com https://googleads.g.doubleclick.net https://www.googleadservices.com https://pagead2.googlesyndication.com https://adservice.google.com https://tpc.googlesyndication.com https://ep2.adtrafficquality.google",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com data:",
            "img-src 'self' data: https:",
            "connect-src 'self' https://api.razorpay.com https://lumberjack.razorpay.com https://www.googletagmanager.com https://www.google-analytics.com https://analytics.google.com https://www.google.com https://googleads.g.doubleclick.net https://pagead2.googlesyndication.com https://adservice.google.com https://ep1.adtrafficquality.google https://ep2.adtrafficquality.google",
            "frame-src 'self' https://api.razorpay.com https://checkout.razorpay.com https://www.googletagmanager.com https://td.doubleclick.net https://googleads.g.doubleclick.net https://tpc.googlesyndication.com https://pagead2.googlesyndication.com https://ep2.adtrafficquality.google https://www.google.com",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self' https://accounts.google.com",
        ]
        response.setdefault("Content-Security-Policy", "; ".join(csp_directives))
        response.setdefault(
            "Permissions-Policy",
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), usb=()",
        )
        response.setdefault("X-Content-Type-Options", "nosniff")
        response.setdefault("X-Frame-Options", "DENY")
        response.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")

        if request.path.startswith(("/api/", "/ads/", "/downloads/", "/dashboard/", "/auth/")):
            response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response["Pragma"] = "no-cache"

        return response


class MaintenanceAndAuditMiddleware:
    """Checks if platform maintenance mode is active while allowing staff access."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if not request.path.startswith(("/admin/", "/static/", "/auth/login/")):
            config = SiteConfiguration.get_solo()
            is_staff = hasattr(request, "user") and request.user.is_authenticated and request.user.is_staff
            if config.maintenance_mode and not is_staff:
                return render(
                    request,
                    "errors/500.html",
                    {
                        "error_title": "Scheduled Platform Maintenance",
                        "error_message": (
                            "InSave Hub is currently undergoing scheduled infrastructure "
                            "calibration. Service will resume shortly."
                        ),
                    },
                    status=503,
                )
        return self.get_response(request)
