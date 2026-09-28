"""User Profile and Security Preferences model for InSave Hub."""
import secrets
from typing import Optional

from django.conf import settings
from django.db import models
from django.utils import timezone


class Profile(models.Model):
    """
    Extended profile associated with a Django User.
    Stores minimal required profile metadata, email verification state,
    and Google OAuth subject identifier without ever storing external passwords.
    """

    class AuthProvider(models.TextChoices):
        EMAIL = "email", "Email & Password"
        GOOGLE = "google", "Google OAuth 2.0"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    display_name = models.CharField(max_length=120, blank=True)
    avatar_url = models.URLField(max_length=500, blank=True)
    auth_provider = models.CharField(
        max_length=24,
        choices=AuthProvider.choices,
        default=AuthProvider.EMAIL,
        db_index=True,
    )
    google_sub_id = models.CharField(
        max_length=128,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
    )

    # Email Verification State
    email_verified = models.BooleanField(default=False, db_index=True)
    email_verification_token = models.CharField(
        max_length=128,
        blank=True,
        db_index=True,
    )
    email_verified_at = models.DateTimeField(null=True, blank=True)

    # Security Preferences
    security_alerts_enabled = models.BooleanField(default=True)
    last_login_ip_hash = models.CharField(max_length=64, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["auth_provider", "email_verified"], name="prof_provider_ver_idx"),
        ]

    def __str__(self) -> str:
        return self.display_name or self.user.username

    @property
    def initials(self) -> str:
        name = (self.display_name or self.user.get_full_name() or self.user.username).strip()
        parts = [p for p in name.split() if p]
        if len(parts) >= 2:
            return (parts[0][0] + parts[1][0]).upper()
        return name[:2].upper() if name else "IH"

    def issue_verification_token(self) -> str:
        token = secrets.token_urlsafe(32)
        self.email_verification_token = token
        self.save(update_fields=["email_verification_token", "updated_at"])
        return token

    def mark_email_verified(self) -> None:
        self.email_verified = True
        self.email_verification_token = ""
        self.email_verified_at = timezone.now()
        self.save(update_fields=["email_verified", "email_verification_token", "email_verified_at", "updated_at"])


def get_or_create_user_profile(user) -> Optional[Profile]:
    """Ensure a Profile record exists for the given authenticated user."""
    if not user or not getattr(user, "is_authenticated", False):
        return None
    profile, _ = Profile.objects.get_or_create(
        user=user,
        defaults={
            "display_name": user.get_full_name() or user.username,
        },
    )
    return profile
