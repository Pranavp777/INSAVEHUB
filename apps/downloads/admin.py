from django.contrib import admin

from apps.downloads.models import Download, DownloadAttempt, Tool


@admin.register(Tool)
class ToolAdmin(admin.ModelAdmin):
    list_display = (
        "display_order",
        "badge_code",
        "name",
        "slug",
        "category",
        "is_active",
        "is_featured",
        "total_uses",
    )
    list_display_links = ("name",)
    list_filter = ("category", "is_active", "is_featured")
    search_fields = ("name", "slug", "short_description")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("display_order", "name")
    actions = ["enable_selected_tools", "disable_selected_tools"]

    @admin.action(description="Enable selected Instagram tools")
    def enable_selected_tools(self, request, queryset) -> None:
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} tool(s) enabled.")

    @admin.action(description="Disable selected Instagram tools")
    def disable_selected_tools(self, request, queryset) -> None:
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} tool(s) disabled.")


@admin.register(Download)
class DownloadAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "shortcode",
        "content_type",
        "tool",
        "user",
        "status",
        "access_mode",
        "file_size_label",
    )
    list_filter = ("status", "content_type", "access_mode", "tool", "created_at")
    search_fields = ("shortcode", "source_url", "media_title", "author_handle", "user__username")
    readonly_fields = ("id", "download_token", "created_at", "completed_at")
    ordering = ("-created_at",)


@admin.register(DownloadAttempt)
class DownloadAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "status",
        "tool",
        "user",
        "raw_url_short",
        "reason",
    )
    list_filter = ("status", "tool", "created_at")
    search_fields = ("raw_url", "normalized_url", "reason", "ip_hash", "user__username")
    readonly_fields = ("id", "created_at")
    ordering = ("-created_at",)

    @admin.display(description="Submitted URL")
    def raw_url_short(self, obj: DownloadAttempt) -> str:
        return obj.raw_url[:60]
