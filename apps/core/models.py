"""Core database models: SiteConfiguration and AuditLog."""
import uuid
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.core.cache import cache
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.http import HttpRequest

from apps.core.utils import get_ip_hash


class SiteConfiguration(models.Model):
    """
    Singleton platform configuration managed via the Django Admin.
    Controls rate limits, advertisement timers, 24-hour free access rules,
    donation presets, and global feature flags.
    """

    singleton_id = models.PositiveSmallIntegerField(default=1, unique=True, editable=False)
    site_name = models.CharField(max_length=80, default="INSTASAVE HUB")
    tagline = models.CharField(
        max_length=160,
        default="Your Instagram Workflow, Refined.",
    )
    maintenance_mode = models.BooleanField(default=False)

    # Access & Interstitial Configuration
    ad_countdown_seconds = models.PositiveIntegerField(
        default=30,
        validators=[MinValueValidator(5), MaxValueValidator(300)],
        help_text="Server-enforced countdown duration in seconds before unlocking next download.",
    )
    free_access_hours = models.PositiveIntegerField(
        default=24,
        validators=[MinValueValidator(1), MaxValueValidator(168)],
        help_text="Duration in hours of uninterrupted access granted after completing an ad session.",
    )
    free_downloads_before_ad = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(20)],
        help_text="Number of completed downloads permitted before triggering the 30-second ad gate.",
    )

    # Feature Flags
    enable_advertisements = models.BooleanField(default=True)
    enable_donations = models.BooleanField(default=True)
    enable_google_oauth = models.BooleanField(default=True)
    enable_guest_downloads = models.BooleanField(default=True)

    # Rate Limiting Rules
    rate_limit_analyze_per_min = models.PositiveIntegerField(default=15)
    rate_limit_download_per_min = models.PositiveIntegerField(default=10)
    rate_limit_auth_per_min = models.PositiveIntegerField(default=8)
    rate_limit_password_reset_per_hour = models.PositiveIntegerField(default=5)
    rate_limit_oauth_per_min = models.PositiveIntegerField(default=10)
    rate_limit_donation_per_min = models.PositiveIntegerField(default=6)

    # Donation Settings
    preset_donation_amounts = models.CharField(
        max_length=120,
        default="100,250,500,1000",
        help_text="Comma-separated preset donation amounts in the configured currency.",
    )
    donation_currency = models.CharField(max_length=8, default="INR")
    minimum_donation_amount = models.PositiveIntegerField(default=50)
    maximum_donation_amount = models.PositiveIntegerField(default=100000)

    # Google AdSense & Search Console Configuration
    adsense_publisher_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Google AdSense Publisher ID (e.g. pub-1234567890123456 or ca-pub-1234567890123456). Falls back to ADSENSE_PUBLISHER_ID environment variable if blank.",
    )
    enable_adsense = models.BooleanField(
        default=True,
        help_text="Master toggle to enable or disable Google AdSense scripts and ad slots site-wide.",
    )
    enable_adsense_auto_ads = models.BooleanField(
        default=True,
        help_text="Enable Google Auto Ads tag in the head section.",
    )
    google_search_console_verification = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Google Search Console verification code (content attribute of google-site-verification meta tag).",
    )

    # Advertisement Sponsor Slot Configuration
    ad_sponsor_title = models.CharField(
        max_length=120,
        default="Edge Media Delivery Infrastructure",
    )
    ad_sponsor_body = models.TextField(
        default=(
            "High-throughput content inspection and zero-retention media routing "
            "supported by our global network sponsors."
        ),
    )
    ad_sponsor_cta_text = models.CharField(max_length=60, default="Learn About Our Architecture")
    ad_sponsor_cta_url = models.URLField(default="https://www.cloudflare.com/")

    # Progressive Web App (PWA) Settings
    pwa_name = models.CharField(
        max_length=120,
        default="INSTASAVE HUB — Instagram Video & Post Downloader",
        help_text="Full application name displayed on device install screens.",
    )
    pwa_short_name = models.CharField(
        max_length=40,
        default="INSTASAVE HUB",
        help_text="Short application name displayed on device home screens.",
    )
    pwa_description = models.TextField(
        default="Download public Instagram Videos, Reels, Photos, and Carousels in 1080p MP4 and JPEG.",
        help_text="Application description provided to PWA installers.",
    )
    pwa_app_icon = models.CharField(
        max_length=255,
        default="/static/images/icon-512.png",
        help_text="Primary app icon path or URL (defaults to /static/images/icon-512.png).",
    )
    pwa_theme_color = models.CharField(
        max_length=16,
        default="#030712",
        help_text="Hex color code for mobile status bar and browser frame (e.g. #030712).",
    )
    pwa_background_color = models.CharField(
        max_length=16,
        default="#030712",
        help_text="Hex color code for splash screen background (e.g. #030712).",
    )
    pwa_install_button_text = models.CharField(
        max_length=40,
        default="Install App",
        help_text="Label on the install button (e.g. Install App or Download App).",
    )
    pwa_start_url = models.CharField(
        max_length=120,
        default="/?source=pwa",
        help_text="Entry URL launched when opening the installed PWA.",
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site Configuration"
        verbose_name_plural = "Site Configuration"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(singleton_id=1),
                name="site_config_singleton_constraint",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.site_name} Configuration"

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.singleton_id = 1
        super().save(*args, **kwargs)
        cache.delete("insave_site_configuration")

    def get_preset_amounts_list(self) -> List[int]:
        amounts: List[int] = []
        for part in self.preset_donation_amounts.split(","):
            part = part.strip()
            if part.isdigit() and int(part) > 0:
                amounts.append(int(part))
        return amounts or [100, 250, 500, 1000]

    def get_adsense_publisher_id(self) -> str:
        """
        Return the canonical publisher ID in 'pub-XXXXXXXXXXXXXXXX' format.
        Checks database configuration first, falls back to settings.ADSENSE_PUBLISHER_ID.
        """
        import re

        raw = (self.adsense_publisher_id or "").strip()
        if not raw:
            raw = getattr(settings, "ADSENSE_PUBLISHER_ID", "").strip()
        if not raw:
            return ""

        clean = re.sub(r"^ca-", "", raw, flags=re.IGNORECASE).strip()
        if not clean.lower().startswith("pub-"):
            clean = f"pub-{clean}"
        return clean

    def get_adsense_client(self) -> str:
        """Return the official Google AdSense client ID string: ca-pub-XXXXXXXXXXXXXXXX."""
        pub_id = self.get_adsense_publisher_id()
        if not pub_id:
            return ""
        return f"ca-{pub_id}"

    def is_adsense_active(self) -> bool:
        """Return whether AdSense is enabled and a publisher ID is configured."""
        return bool(self.enable_adsense and self.get_adsense_publisher_id())

    def get_search_console_verification(self) -> str:
        """Return Google Search Console verification meta tag token."""
        code = (self.google_search_console_verification or "").strip()
        if not code:
            code = getattr(settings, "GOOGLE_SEARCH_CONSOLE_VERIFICATION", "").strip()
        return code

    def get_pwa_theme_color(self) -> str:
        """Return safe hex color string for theme-color."""
        color = (self.pwa_theme_color or "").strip()
        return color if color.startswith("#") and len(color) in (4, 7) else "#030712"

    def get_pwa_background_color(self) -> str:
        """Return safe hex color string for background-color."""
        color = (self.pwa_background_color or "").strip()
        return color if color.startswith("#") and len(color) in (4, 7) else "#030712"

    def get_pwa_install_button_text(self) -> str:
        """Return label for install trigger button."""
        return (self.pwa_install_button_text or "").strip() or "Install App"

    def get_pwa_manifest(self) -> Dict[str, Any]:
        """Return complete W3C-compliant Web App Manifest dictionary."""
        theme_color = self.get_pwa_theme_color()
        bg_color = self.get_pwa_background_color()
        start_url = (self.pwa_start_url or "").strip() or "/?source=pwa"
        app_icon = (self.pwa_app_icon or "").strip() or "/static/images/icon-512.png"

        return {
            "id": "/",
            "name": (self.pwa_name or "").strip() or "INSTASAVE HUB — Instagram Video & Post Downloader",
            "short_name": (self.pwa_short_name or "").strip() or "INSTASAVE HUB",
            "description": (self.pwa_description or "").strip() or "Download public Instagram Videos, Reels, Photos, and Carousels in 1080p MP4 and JPEG.",
            "start_url": start_url,
            "scope": "/",
            "display": "standalone",
            "orientation": "any",
            "background_color": bg_color,
            "theme_color": theme_color,
            "categories": ["utilities", "photo", "video", "productivity"],
            "icons": [
                {
                    "src": "/static/images/icon-192.png",
                    "sizes": "192x192",
                    "type": "image/png",
                    "purpose": "any",
                },
                {
                    "src": "/static/images/icon-192.png",
                    "sizes": "192x192",
                    "type": "image/png",
                    "purpose": "maskable",
                },
                {
                    "src": app_icon,
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "any",
                },
                {
                    "src": app_icon,
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "maskable",
                },
                {
                    "src": "/static/images/logo.png",
                    "sizes": "256x256",
                    "type": "image/png",
                    "purpose": "any",
                },
            ],
            "shortcuts": [
                {
                    "name": "Instagram Downloader",
                    "short_name": "Download",
                    "description": "Preview and download Instagram Videos and Reels",
                    "url": "/downloads/",
                    "icons": [{"src": "/static/images/icon-192.png", "sizes": "192x192"}],
                },
                {
                    "name": "Media Suite Tools",
                    "short_name": "Tools",
                    "description": "Instagram media extraction suite",
                    "url": "/tools/",
                    "icons": [{"src": "/static/images/icon-192.png", "sizes": "192x192"}],
                },
            ],
        }

    @classmethod
    def get_solo(cls) -> "SiteConfiguration":
        cached = cache.get("insave_site_configuration")
        if cached is not None:
            return cached
        try:
            obj, _ = cls.objects.get_or_create(
                singleton_id=1,
                defaults={
                    "ad_countdown_seconds": getattr(settings, "AD_COUNTDOWN_SECONDS", 30),
                    "free_access_hours": getattr(settings, "FREE_ACCESS_HOURS", 24),
                    "free_downloads_before_ad": getattr(settings, "FREE_DOWNLOADS_BEFORE_AD", 1),
                    "donation_currency": getattr(settings, "DONATION_CURRENCY", "INR"),
                },
            )
            cache.set("insave_site_configuration", obj, timeout=120)
            return obj
        except Exception:
            return cls(
                singleton_id=1,
                ad_countdown_seconds=getattr(settings, "AD_COUNTDOWN_SECONDS", 30),
                free_access_hours=getattr(settings, "FREE_ACCESS_HOURS", 24),
                free_downloads_before_ad=getattr(settings, "FREE_DOWNLOADS_BEFORE_AD", 1),
                donation_currency=getattr(settings, "DONATION_CURRENCY", "INR"),
            )


class AuditLog(models.Model):
    """
    Immutable security and operational audit log for tracking authentication,
    rate limit violations, administrative actions, payment events, and system errors.
    """

    class Severity(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"
        CRITICAL = "critical", "Critical"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    event_type = models.CharField(max_length=64, db_index=True)
    severity = models.CharField(
        max_length=16,
        choices=Severity.choices,
        default=Severity.INFO,
        db_index=True,
    )
    actor_ip_hash = models.CharField(max_length=64, db_index=True, blank=True)
    resource_type = models.CharField(max_length=64, blank=True)
    resource_id = models.CharField(max_length=128, blank=True)
    description = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    path = models.CharField(max_length=255, blank=True)
    method = models.CharField(max_length=16, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["event_type", "-created_at"], name="audit_evt_created_idx"),
            models.Index(fields=["severity", "-created_at"], name="audit_sev_created_idx"),
        ]

    def __str__(self) -> str:
        return f"[{self.severity.upper()}] {self.event_type} at {self.created_at:%Y-%m-%d %H:%M:%S}"

    @classmethod
    def record(
        cls,
        event_type: str,
        description: str,
        request: Optional[HttpRequest] = None,
        user: Optional[Any] = None,
        severity: str = Severity.INFO,
        resource_type: str = "",
        resource_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional["AuditLog"]:
        try:
            resolved_user = user
            ip_hash = ""
            path = ""
            method = ""
            if request is not None:
                if resolved_user is None and hasattr(request, "user") and request.user.is_authenticated:
                    resolved_user = request.user
                ip_hash = get_ip_hash(request)
                path = request.path[:255]
                method = (request.method or "")[:16]

            return cls.objects.create(
                user=resolved_user if (resolved_user and getattr(resolved_user, "pk", None)) else None,
                event_type=event_type[:64],
                severity=severity,
                actor_ip_hash=ip_hash,
                resource_type=resource_type[:64],
                resource_id=str(resource_id)[:128],
                description=description,
                metadata=metadata or {},
                path=path,
                method=method,
            )
        except Exception:
            return None
