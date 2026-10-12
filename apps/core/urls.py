from django.urls import path

from apps.core import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about_view, name="about"),
    path("contact/", views.contact_view, name="contact"),
    path("privacy/", views.privacy_view, name="privacy"),
    path("privacy-policy/", views.privacy_view, name="privacy_policy"),
    path("terms/", views.terms_view, name="terms"),
    path("terms-of-service/", views.terms_view, name="terms_of_service"),
    path("terms-and-conditions/", views.terms_view, name="terms_and_conditions"),
    path("disclaimer/", views.disclaimer_view, name="disclaimer"),
    path("dmca/", views.dmca_view, name="dmca"),
    path("faq/", views.faq_view, name="faq"),
    path("robots.txt", views.robots_txt, name="robots_txt"),
    path("ads.txt", views.ads_txt, name="ads_txt"),
    path("sitemap.xml", views.sitemap_xml, name="sitemap_xml"),
    path("manifest.json", views.web_manifest, name="manifest_json"),
    path("manifest.webmanifest", views.web_manifest, name="web_manifest"),
    path("service-worker.js", views.service_worker, name="service_worker_root"),
    path("sw.js", views.service_worker, name="service_worker"),
    path("offline/", views.offline_view, name="offline"),
    path("health/", views.health_check, name="health_check"),
]
