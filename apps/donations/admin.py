from django.contrib import admin

from apps.donations.models import Donation


@admin.register(Donation)
class DonationAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "provider_order_id",
        "public_donor_label",
        "amount",
        "currency",
        "is_anonymous",
        "provider",
        "status",
        "completed_at",
    )
    list_filter = ("status", "provider", "is_anonymous", "currency", "created_at")
    search_fields = (
        "provider_order_id",
        "provider_payment_id",
        "donor_name",
        "donor_email",
        "user__username",
    )
    readonly_fields = (
        "id",
        "provider_order_id",
        "provider_payment_id",
        "provider_signature",
        "ip_hash",
        "created_at",
        "completed_at",
    )
    ordering = ("-created_at",)
