"""Database models for DownloadSession, 5s/30s AdSession, and 24-hour FreeAccessSession."""
import math
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


def generate_ad_nonce() -> str:
    return secrets.token_urlsafe(32)


class DownloadSession(models.Model):
    """
    Tracks per-user/session download state, first-download completion,
    30-second advertisement completion, and 24-hour ad-free access timestamps
    validated strictly against the server clock.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="download_sessions",
    )
    session_key = models.CharField(max_length=64, db_index=True, blank=True)
    ip_hash = models.CharField(max_length=64, db_index=True, blank=True)
    first_download_completed = models.BooleanField(default=False, db_index=True)
    ad_completed = models.BooleanField(default=False, db_index=True)
    ad_completed_at = models.DateTimeField(null=True, blank=True)
    access_started_at = models.DateTimeField(null=True, blank=True)
    access_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Download Session"
        verbose_name_plural = "Download Sessions"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["user", "access_expires_at"], name="dlsess_user_exp_idx"),
            models.Index(fields=["session_key", "access_expires_at"], name="dlsess_key_exp_idx"),
        ]

    def __str__(self) -> str:
        actor = self.user.username if self.user else f"session:{self.session_key[:8]}"
        return f"DownloadSession({actor}, first_done={self.first_download_completed}, ad_done={self.ad_completed})"

    @property
    def has_active_24h_access(self) -> bool:
        if not self.access_expires_at:
            return False
        return timezone.now() < self.access_expires_at

    @property
    def remaining_seconds(self) -> int:
        if not self.access_expires_at:
            return 0
        delta = int((self.access_expires_at - timezone.now()).total_seconds())
        return max(0, delta)

    @property
    def formatted_remaining(self) -> str:
        total = self.remaining_seconds
        hours = total // 3600
        minutes = (total % 3600) // 60
        seconds = total % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


class AdSession(models.Model):
    """
    Server-anchored 5-second or 30-second advertisement/interstitial session.
    Tracks `started_at` and `eligible_at` on the server so client refreshes
    or JavaScript tampering cannot bypass the required wait time.
    """

    class AdType(models.TextChoices):
        INITIAL_5S = "initial_5s", "5-Second Initial Download Ad"
        UNLOCK_30S = "unlock_30s", "30-Second 24-Hour Unlock Ad"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active Countdown"
        COMPLETED = "completed", "Completed"
        EXPIRED = "expired", "Expired"
        INVALIDATED = "invalidated", "Invalidated"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="ad_sessions",
    )
    session_key = models.CharField(max_length=64, db_index=True, blank=True)
    ip_hash = models.CharField(max_length=64, db_index=True, blank=True)
    pending_download = models.ForeignKey(
        "downloads.Download",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ad_sessions",
    )
    ad_type = models.CharField(
        max_length=16,
        choices=AdType.choices,
        default=AdType.UNLOCK_30S,
        db_index=True,
    )
    nonce_token = models.CharField(
        max_length=128,
        default=generate_ad_nonce,
        unique=True,
        db_index=True,
    )
    required_duration_seconds = models.PositiveIntegerField(default=30)
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    eligible_at = models.DateTimeField(db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Advertisement Session"
        verbose_name_plural = "Advertisement Sessions"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["user", "status", "-started_at"], name="ad_user_status_idx"),
            models.Index(fields=["session_key", "status", "-started_at"], name="ad_sess_status_idx"),
        ]

    def __str__(self) -> str:
        actor = self.user.username if self.user else f"session:{self.session_key[:8]}"
        return f"AdSession({actor}, {self.ad_type}, {self.status}, {self.required_duration_seconds}s)"

    def save(self, *args, **kwargs) -> None:
        if not self.started_at:
            self.started_at = timezone.now()
        if not self.eligible_at:
            self.eligible_at = self.started_at + timedelta(seconds=self.required_duration_seconds)
        super().save(*args, **kwargs)

    @property
    def remaining_seconds(self) -> int:
        if self.status != self.Status.ACTIVE:
            return 0
        delta = (self.eligible_at - timezone.now()).total_seconds()
        return max(0, int(math.ceil(delta)))

    @property
    def is_ready_to_complete(self) -> bool:
        return self.status == self.Status.ACTIVE and timezone.now() >= self.eligible_at


class FreeAccessSession(models.Model):
    """
    Server-validated 24-hour free access window unlocked after completing a 30-second AdSession.
    During this active window, users can perform eligible downloads without
    repeatedly encountering advertisements.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="free_access_sessions",
    )
    session_key = models.CharField(max_length=64, db_index=True, blank=True)
    ip_hash = models.CharField(max_length=64, db_index=True, blank=True)
    source_ad_session = models.OneToOneField(
        AdSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_free_session",
    )
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    downloads_used_count = models.PositiveIntegerField(default=0)
    revoked_reason = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "24-Hour Free Access Session"
        verbose_name_plural = "24-Hour Free Access Sessions"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["user", "is_active", "expires_at"], name="free_user_active_exp_idx"),
            models.Index(
                fields=["session_key", "is_active", "expires_at"],
                name="free_sess_active_exp_idx",
            ),
        ]

    def __str__(self) -> str:
        actor = self.user.username if self.user else f"session:{self.session_key[:8]}"
        return f"FreeAccessSession({actor}, expires={self.expires_at:%Y-%m-%d %H:%M:%S})"

    @property
    def remaining_seconds(self) -> int:
        if not self.is_active:
            return 0
        delta = int((self.expires_at - timezone.now()).total_seconds())
        return max(0, delta)

    @property
    def formatted_remaining(self) -> str:
        total = self.remaining_seconds
        hours = total // 3600
        minutes = (total % 3600) // 60
        seconds = total % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def check_and_sync_expiration(self) -> bool:
        """
        Verify if this session is still valid on the server clock.
        If expired, deactivates it in the database and returns False.
        """
        if self.is_active and timezone.now() >= self.expires_at:
            self.is_active = False
            self.save(update_fields=["is_active"])
            return False
        return self.is_active
