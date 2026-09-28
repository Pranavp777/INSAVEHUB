"""Database model for platform Donations and payment gateway transactions."""
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Donation(models.Model):
    """
    Represents a voluntary one-time contribution to support InSave Hub.
    Supports Razorpay order creation, HMAC-SHA256 signature verification,
    anonymous donor preferences, and full payment lifecycle tracking.
    """

    class Status(models.TextChoices):
        CREATED = "created", "Order Created"
        PENDING = "pending", "Payment Pending"
        COMPLETED = "completed", "Verified & Completed"
        FAILED = "failed", "Payment Failed"
        REFUNDED = "refunded", "Refunded"

    class Provider(models.TextChoices):
        RAZORPAY = "razorpay", "Razorpay"
        CUSTOM = "custom", "Configured Gateway"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="donations",
    )
    donor_name = models.CharField(max_length=120, blank=True)
    donor_email = models.EmailField(blank=True)
    is_anonymous = models.BooleanField(default=False, db_index=True)
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("1.00"))],
    )
    currency = models.CharField(max_length=8, default="INR")
    message = models.CharField(max_length=280, blank=True)
    provider = models.CharField(
        max_length=24,
        choices=Provider.choices,
        default=Provider.RAZORPAY,
    )
    provider_order_id = models.CharField(max_length=128, unique=True, db_index=True)
    provider_payment_id = models.CharField(max_length=128, blank=True, db_index=True)
    provider_signature = models.CharField(max_length=256, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.CREATED,
        db_index=True,
    )
    ip_hash = models.CharField(max_length=64, blank=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Donation"
        verbose_name_plural = "Donations"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"], name="don_status_created_idx"),
            models.Index(fields=["user", "-created_at"], name="don_user_created_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="donation_positive_amount_constraint",
            ),
        ]

    def __str__(self) -> str:
        display_donor = "Anonymous Supporter" if self.is_anonymous else (self.donor_name or "Supporter")
        return f"{self.currency} {self.amount} by {display_donor} ({self.status})"

    @property
    def public_donor_label(self) -> str:
        if self.is_anonymous:
            return "Anonymous Supporter"
        if self.donor_name:
            return self.donor_name
        if self.user:
            return self.user.username
        return "Platform Supporter"
