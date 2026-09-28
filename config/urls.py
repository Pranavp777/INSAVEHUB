"""Root URL Configuration for InSave Hub."""
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "InSave Hub Platform Administration"
admin.site.site_title = "InSave Hub Admin"
admin.site.index_title = "Control Surface & Database Management"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.core.urls", namespace="core")),
    path("auth/", include("apps.accounts.urls", namespace="accounts")),
    path("", include("apps.downloads.urls", namespace="downloads")),
    path("ads/", include("apps.advertisements.urls", namespace="advertisements")),
    path("", include("apps.donations.urls", namespace="donations")),
    path("dashboard/", include("apps.dashboard.urls", namespace="dashboard")),
]

handler400 = "apps.core.views.error_400"
handler403 = "apps.core.views.error_403"
handler404 = "apps.core.views.error_404"
handler500 = "apps.core.views.error_500"
