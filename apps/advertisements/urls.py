from django.urls import path

from apps.advertisements import views

app_name = "advertisements"

urlpatterns = [
    path("gate/", views.ad_gate_view, name="gate"),
    path("status/<str:session_id>/", views.ad_status_api, name="status"),
    path("complete/", views.ad_complete_view, name="complete"),
]
