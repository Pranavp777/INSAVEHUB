from django.urls import path

from apps.core import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("robots.txt", views.robots_txt, name="robots_txt"),
    path("ads.txt", views.ads_txt, name="ads_txt"),
    path("sitemap.xml", views.sitemap_xml, name="sitemap_xml"),
    path("manifest.webmanifest", views.web_manifest, name="web_manifest"),
    path("sw.js", views.service_worker, name="service_worker"),
    path("health/", views.health_check, name="health_check"),
]
