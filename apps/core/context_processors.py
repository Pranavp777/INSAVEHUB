"""Template context processors for global site configuration, SEO, and access state."""
from typing import Any, Dict

from django.conf import settings
from django.http import HttpRequest

from apps.core.models import SiteConfiguration


def site_context(request: HttpRequest) -> Dict[str, Any]:
    """Provide global site settings, canonical URLs, and current user access status."""
    config = SiteConfiguration.get_solo()
    canonical_base = getattr(settings, "CANONICAL_BASE_URL", "http://localhost:8000").rstrip("/")
    canonical_url = f"{canonical_base}{request.path}"

    access_summary: Dict[str, Any] = {
        "mode": "initial_free",
        "has_free_24h": False,
        "free_24h_remaining_seconds": 0,
        "free_24h_formatted": "00:00:00",
        "ad_required": False,
        "active_ad_session_id": None,
    }

    try:
        from apps.advertisements.services import get_user_access_summary

        access_summary = get_user_access_summary(request)
    except Exception:
        pass

    return {
        "site_config": config,
        "canonical_url": canonical_url,
        "canonical_base_url": canonical_base,
        "google_oauth_configured": bool(
            config.enable_google_oauth and getattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "")
        ),
        "access_state": access_summary,
        "adsense_publisher_id": config.get_adsense_publisher_id(),
        "adsense_client": config.get_adsense_client(),
        "adsense_enabled": config.is_adsense_active(),
        "adsense_auto_ads": bool(config.is_adsense_active() and config.enable_adsense_auto_ads),
        "google_search_console_verification": config.get_search_console_verification(),
    }
