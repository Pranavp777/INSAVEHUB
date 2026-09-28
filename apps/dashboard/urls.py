from django.urls import path

from apps.dashboard import views

app_name = "dashboard"

urlpatterns = [
    path("", views.dashboard_index_view, name="index"),
    path("admin-analytics/", views.admin_analytics_view, name="admin_analytics"),
]
