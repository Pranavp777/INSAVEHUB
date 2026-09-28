from django.contrib import admin

from apps.accounts.models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "display_name",
        "auth_provider",
        "email_verified",
        "security_alerts_enabled",
        "created_at",
    )
    list_filter = ("auth_provider", "email_verified", "security_alerts_enabled", "created_at")
    search_fields = ("user__username", "user__email", "display_name", "google_sub_id")
    readonly_fields = ("created_at", "updated_at", "email_verified_at", "last_login_ip_hash")
