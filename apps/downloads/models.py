"""Database models for Instagram Utility Tools, Downloads, and DownloadAttempts."""
import secrets
import uuid

from django.conf import settings
from django.db import models


def generate_download_token() -> str:
    return secrets.token_urlsafe(32)


class Tool(models.Model):
    """
    Represents an Instagram content utility module managed via the Admin.
    """

    class Category(models.TextChoices):
        REEL = "reel", "Reel Utility"
        VIDEO = "video", "Video Utility"
        IMAGE = "image", "Image Utility"
        POST = "post", "Public Post Utility"
        PROFILE = "profile", "Profile Media Utility"
        METADATA = "metadata", "Content Information Extractor"

    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=120, unique=True, db_index=True)
    category = models.CharField(
        max_length=24,
        choices=Category.choices,
        default=Category.REEL,
        db_index=True,
    )
    short_description = models.CharField(max_length=220)
    detailed_description = models.TextField()
    supported_url_hint = models.CharField(
        max_length=160,
        default="https://www.instagram.com/reel/C8xYz123AbC/",
    )
    output_formats = models.CharField(
        max_length=120,
        default="MP4 (H.264) / Original Audio",
    )
    badge_code = models.CharField(max_length=16, default="MOD-01")
    is_active = models.BooleanField(default=True, db_index=True)
    is_featured = models.BooleanField(default=True)
    display_order = models.PositiveSmallIntegerField(default=1)
    total_uses = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Instagram Tool"
        verbose_name_plural = "Instagram Tools"
        ordering = ["display_order", "name"]
        indexes = [
            models.Index(fields=["is_active", "display_order"], name="tool_active_ord_idx"),
        ]

    def __str__(self) -> str:
        return self.name


class Download(models.Model):
    """
    Tracks an analyzed and authorized public Instagram media download record.
    Enforces server-side token authorization and records the access mode used.
    """

    class ContentType(models.TextChoices):
        REEL = "reel", "Instagram Reel"
        VIDEO = "video", "Instagram Video"
        IMAGE = "image", "Instagram Photograph"
        POST = "post", "Public Post / Carousel"
        PROFILE = "profile", "Public Profile Media"
        METADATA = "metadata", "Content Information Package"

    class Status(models.TextChoices):
        READY = "ready", "Analyzed & Ready"
        AD_LOCKED = "ad_locked", "Awaiting 30s Advertisement"
        COMPLETED = "completed", "Download Completed"
        FAILED = "failed", "Failed"
        EXPIRED = "expired", "Expired"

    class AccessMode(models.TextChoices):
        INITIAL_FREE = "initial_free", "Initial Free Allowance"
        AD_UNLOCKED = "ad_unlocked", "30s Ad Unlocked"
        FREE_24H_PASS = "free_24h_pass", "24-Hour Free Access Pass"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="downloads",
    )
    session_key = models.CharField(max_length=64, db_index=True, blank=True)
    ip_hash = models.CharField(max_length=64, db_index=True, blank=True)
    tool = models.ForeignKey(
        Tool,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="downloads",
    )
    source_url = models.URLField(max_length=500)
    shortcode = models.CharField(max_length=64, db_index=True)
    content_type = models.CharField(
        max_length=24,
        choices=ContentType.choices,
        default=ContentType.REEL,
        db_index=True,
    )
    media_format = models.CharField(max_length=80, default="MP4 1080p")
    resolution = models.CharField(max_length=40, default="1080x1920")
    file_size_bytes = models.BigIntegerField(default=0)
    file_size_label = models.CharField(max_length=32, default="8.4 MB")
    media_title = models.CharField(max_length=240)
    author_handle = models.CharField(max_length=80, blank=True)
    preview_metadata = models.JSONField(default=dict, blank=True)
    download_token = models.CharField(
        max_length=128,
        default=generate_download_token,
        unique=True,
        db_index=True,
    )
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.READY,
        db_index=True,
    )
    access_mode = models.CharField(
        max_length=24,
        choices=AccessMode.choices,
        default=AccessMode.INITIAL_FREE,
    )
    completed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Download"
        verbose_name_plural = "Downloads"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status", "-created_at"], name="dl_user_status_idx"),
            models.Index(fields=["session_key", "status", "-created_at"], name="dl_sess_status_idx"),
            models.Index(fields=["shortcode", "-created_at"], name="dl_shortcode_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.get_content_type_display()} [{self.shortcode}] ({self.status})"


class DownloadAttempt(models.Model):
    """
    Granular telemetry and security log for every URL analysis or download execution attempt.
    """

    class AttemptStatus(models.TextChoices):
        ALLOWED = "allowed", "Allowed"
        BLOCKED_AD_REQUIRED = "blocked_ad_required", "Blocked (30s Ad Required)"
        BLOCKED_RATE_LIMIT = "blocked_rate_limit", "Blocked (Rate Limited)"
        INVALID_URL = "invalid_url", "Rejected (Invalid URL)"
        RESTRICTED_CONTENT = "restricted_content", "Rejected (Private/Restricted)"
        COMPLETED = "completed", "Download Completed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="download_attempts",
    )
    tool = models.ForeignKey(
        Tool,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attempts",
    )
    download = models.ForeignKey(
        Download,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attempts",
    )
    raw_url = models.CharField(max_length=500)
    normalized_url = models.CharField(max_length=500, blank=True)
    ip_hash = models.CharField(max_length=64, db_index=True)
    status = models.CharField(
        max_length=32,
        choices=AttemptStatus.choices,
        db_index=True,
    )
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Download Attempt"
        verbose_name_plural = "Download Attempts"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"], name="dl_att_status_idx"),
            models.Index(fields=["ip_hash", "-created_at"], name="dl_att_ip_idx"),
        ]

    def __str__(self) -> str:
        return f"Attempt({self.status}) on {self.raw_url[:40]}"
