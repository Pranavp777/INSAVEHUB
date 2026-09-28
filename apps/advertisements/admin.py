from django.contrib import admin

from apps.advertisements.models import AdSession, FreeAccessSession


@admin.register(AdSession)
class AdSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "status",
        "required_duration_seconds",
        "started_at",
        "eligible_at",
        "completed_at",
    )
    list_filter = ("status", "required_duration_seconds", "started_at")
    search_fields = ("id", "user__username", "user__email", "session_key", "ip_hash")
    readonly_fields = ("id", "nonce_token", "created_at")
    ordering = ("-started_at",)


@admin.register(FreeAccessSession)
class FreeAccessSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "is_active",
        "started_at",
        "expires_at",
        "downloads_used_count",
        "formatted_remaining_display",
    )
    list_filter = ("is_active", "started_at", "expires_at")
    search_fields = ("id", "user__username", "user__email", "session_key", "ip_hash")
    readonly_fields = ("id", "created_at")
    ordering = ("-started_at",)
    actions = ["revoke_selected_sessions"]

    @admin.display(description="Time Remaining")
    def formatted_remaining_display(self, obj: FreeAccessSession) -> str:
        return obj.formatted_remaining

    @admin.action(description="Revoke selected 24-hour free access sessions")
    def revoke_selected_sessions(self, request, queryset) -> None:
        updated = queryset.update(is_active=False, revoked_reason="Revoked by administrator")
        self.message_user(request, f"{updated} free-access session(s) revoked.")
