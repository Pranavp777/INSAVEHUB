from django.contrib import admin
from django.http import HttpRequest

from apps.core.models import AuditLog, SiteConfiguration


@admin.register(SiteConfiguration)
class SiteConfigurationAdmin(admin.ModelAdmin):
    list_display = (
        "site_name",
        "ad_countdown_seconds",
        "free_access_hours",
        "free_downloads_before_ad",
        "enable_advertisements",
        "enable_donations",
        "maintenance_mode",
        "updated_at",
    )
    fieldsets = (
        (
            "Brand & Status",
            {
                "fields": (
                    "site_name",
                    "tagline",
                    "maintenance_mode",
                )
            },
        ),
        (
            "Access & Interstitial Rules",
            {
                "fields": (
                    "enable_advertisements",
                    "ad_countdown_seconds",
                    "free_access_hours",
                    "free_downloads_before_ad",
                    "enable_guest_downloads",
                )
            },
        ),
        (
            "Advertisement Sponsor Content",
            {
                "fields": (
                    "ad_sponsor_title",
                    "ad_sponsor_body",
                    "ad_sponsor_cta_text",
                    "ad_sponsor_cta_url",
                )
            },
        ),
        (
            "Donation & Payment Settings",
            {
                "fields": (
                    "enable_donations",
                    "donation_currency",
                    "preset_donation_amounts",
                    "minimum_donation_amount",
                    "maximum_donation_amount",
                )
            },
        ),
        (
            "Authentication & Rate Limits",
            {
                "fields": (
                    "enable_google_oauth",
                    "rate_limit_analyze_per_min",
                    "rate_limit_download_per_min",
                    "rate_limit_auth_per_min",
                    "rate_limit_password_reset_per_hour",
                    "rate_limit_oauth_per_min",
                    "rate_limit_donation_per_min",
                )
            },
        ),
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        if SiteConfiguration.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "severity",
        "event_type",
        "user",
        "path",
        "method",
        "actor_ip_hash_short",
    )
    list_filter = ("severity", "event_type", "method", "created_at")
    search_fields = ("event_type", "description", "path", "actor_ip_hash", "user__username", "user__email")
    readonly_fields = (
        "id",
        "user",
        "event_type",
        "severity",
        "actor_ip_hash",
        "resource_type",
        "resource_id",
        "description",
        "metadata",
        "path",
        "method",
        "created_at",
    )
    ordering = ("-created_at",)

    @admin.display(description="Actor IP Hash")
    def actor_ip_hash_short(self, obj: AuditLog) -> str:
        return f"{obj.actor_ip_hash[:14]}..." if obj.actor_ip_hash else "-"

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return False
