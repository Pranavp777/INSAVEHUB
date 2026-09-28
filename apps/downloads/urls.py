from django.urls import path

from apps.downloads import views

app_name = "downloads"

urlpatterns = [
    path("tools/", views.tools_list_view, name="tools_list"),
    path("tools/<slug:slug>/", views.tool_detail_view, name="tool_detail"),
    path("downloads/", views.download_interface_view, name="interface"),
    path("downloads/history/", views.download_history_view, name="history"),
    path("downloads/execute/<str:token>/", views.execute_download_view, name="execute"),
    path("api/downloads/analyze/", views.analyze_url_api, name="analyze_api"),
]
