"""Views for landing page, SEO endpoints (robots.txt, sitemap.xml), and error handlers."""
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from apps.core.models import SiteConfiguration
from apps.downloads.models import Tool
from apps.downloads.services import ensure_default_tools


def home(request: HttpRequest) -> HttpResponse:
    """Render the Glass Orbit Landing Page with interactive utility preview."""
    ensure_default_tools()
    tools = Tool.objects.filter(is_active=True).order_by("display_order", "name")
    config = SiteConfiguration.get_solo()

    faqs = [
        {
            "question": "What Instagram links can I download?",
            "answer": (
                "You can download public Instagram Videos, Reels, Single Photos, Multi-Slide "
                "Carousels, and Public Profile Avatars in full HD quality."
            ),
        },
        {
            "question": "How does the 24-hour free access pass work?",
            "answer": (
                "Your first download is immediate. Completing a single 30-second sponsor screen "
                "unlocks 24 hours of uninterrupted downloads."
            ),
        },
        {
            "question": "Do I need to log into my Instagram account?",
            "answer": (
                "No. Simply copy and paste any public Instagram Post, Reel, or Video link into "
                "the downloader box to save the media directly to your device."
            ),
        },
        {
            "question": "Can I install InSave Hub as an app on my phone or computer?",
            "answer": (
                "Yes. Click the Install App button in the top navigation bar to add InSave Hub "
                "to your desktop or mobile home screen."
            ),
        },
    ]

    context = {
        "page_title": "InSave Hub | Your Instagram Workflow, Refined.",
        "meta_description": (
            "Fast Instagram Video, Reel, Photo, and Post downloader."
        ),
        "tools": tools,
        "preset_amounts": config.get_preset_amounts_list(),
        "faqs": faqs,
    }
    return render(request, "home.html", context)


def robots_txt(request: HttpRequest) -> HttpResponse:
    """Serve robots.txt for search engine crawlers."""
    base_url = getattr(settings, "CANONICAL_BASE_URL", "http://localhost:8000").rstrip("/")
    lines = [
        "User-agent: *",
        "Allow: /",
        "Allow: /tools/",
        "Allow: /downloads/",
        "Allow: /donations/",
        "Disallow: /admin/",
        "Disallow: /api/",
        "Disallow: /dashboard/",
        "Disallow: /ads/",
        f"Sitemap: {base_url}/sitemap.xml",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")


def sitemap_xml(request: HttpRequest) -> HttpResponse:
    """Serve dynamic XML sitemap for public pages and utility tools."""
    ensure_default_tools()
    base_url = getattr(settings, "CANONICAL_BASE_URL", "http://localhost:8000").rstrip("/")
    now_iso = timezone.now().strftime("%Y-%m-%d")

    static_paths = [
        reverse("core:home"),
        reverse("downloads:tools_list"),
        reverse("downloads:interface"),
        reverse("donations:index"),
        reverse("accounts:login"),
        reverse("accounts:register"),
    ]

    urls_xml = []
    for path in static_paths:
        priority = "1.0" if path == "/" else "0.8"
        urls_xml.append(
            f"  <url>\n"
            f"    <loc>{base_url}{path}</loc>\n"
            f"    <lastmod>{now_iso}</lastmod>\n"
            f"    <changefreq>weekly</changefreq>\n"
            f"    <priority>{priority}</priority>\n"
            f"  </url>"
        )

    for tool in Tool.objects.filter(is_active=True):
        tool_path = reverse("downloads:tool_detail", kwargs={"slug": tool.slug})
        urls_xml.append(
            f"  <url>\n"
            f"    <loc>{base_url}{tool_path}</loc>\n"
            f"    <lastmod>{now_iso}</lastmod>\n"
            f"    <changefreq>weekly</changefreq>\n"
            f"    <priority>0.7</priority>\n"
            f"  </url>"
        )

    xml_body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls_xml)
        + "\n</urlset>"
    )
    return HttpResponse(xml_body, content_type="application/xml; charset=utf-8")


def health_check(request: HttpRequest) -> JsonResponse:
    """Edge health probe endpoint for Cloudflare Workers and uptime monitors."""
    return JsonResponse(
        {
            "status": "operational",
            "service": "insave-hub",
            "timestamp": timezone.now().isoformat(),
        }
    )


def web_manifest(request: HttpRequest) -> JsonResponse:
    """Serve the Progressive Web App (PWA) manifest for desktop and mobile installation."""
    manifest = {
        "name": "InSave Hub — Instagram Video & Post Downloader",
        "short_name": "InSave Hub",
        "description": "Download public Instagram Videos, Reels, Photos, and Carousels in 1080p MP4 and JPEG.",
        "start_url": "/?source=pwa",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait-primary",
        "background_color": "#F0F9FF",
        "theme_color": "#0284C7",
        "categories": ["utilities", "photo", "video", "productivity"],
        "icons": [
            {
                "src": "/static/images/icon-192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable",
            },
            {
                "src": "/static/images/icon-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable",
            },
            {
                "src": "/static/images/logo-mark.svg",
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "any",
            },
        ],
    }
    return JsonResponse(
        manifest,
        content_type="application/manifest+json; charset=utf-8",
    )


def service_worker(request: HttpRequest) -> HttpResponse:
    """Serve the root-scoped Service Worker for PWA installability and asset caching."""
    sw_script = """const CACHE_NAME = 'insave-hub-pwa-v3';
const PRECACHE_URLS = [
  '/static/images/logo-mark.svg',
  '/static/images/icon-192.png',
  '/static/images/icon-512.png'
];

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS).catch(() => {}))
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      fetch(event.request)
        .then((res) => {
          const clone = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          return res;
        })
        .catch(() => caches.match(event.request))
    );
  }
});
"""
    response = HttpResponse(sw_script, content_type="application/javascript; charset=utf-8")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response



def error_400(request: HttpRequest, exception: Any = None) -> HttpResponse:
    return render(
        request,
        "errors/400.html",
        {
            "error_code": "400",
            "error_title": "Malformed Request Payload",
            "error_message": (
                "The server could not interpret the structure of your request. "
                "Please verify the submitted parameters or URL format and try again."
            ),
        },
        status=400,
    )


def error_403(request: HttpRequest, exception: Any = None) -> HttpResponse:
    return render(
        request,
        "errors/403.html",
        {
            "error_code": "403",
            "error_title": "Access Authorization Denied",
            "error_message": (
                "Your current session does not hold authorization for this resource, "
                "or the security verification token has expired."
            ),
        },
        status=403,
    )


def error_404(request: HttpRequest, exception: Any = None) -> HttpResponse:
    return render(
        request,
        "errors/404.html",
        {
            "error_code": "404",
            "error_title": "Requested Coordinate Not Found",
            "error_message": (
                "The page or media artifact you requested does not exist at this address "
                "or has been relocated within the platform."
            ),
        },
        status=404,
    )


def error_429(request: HttpRequest, exception: Any = None) -> HttpResponse:
    return render(
        request,
        "errors/429.html",
        {
            "error_code": "429",
            "error_title": "Request Rate Limit Reached",
            "error_message": (
                "You have sent too many requests in a short window. "
                "Please wait briefly for the rate limiter window to reset."
            ),
            "retry_after_seconds": 60,
        },
        status=429,
    )


def error_500(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "errors/500.html",
        {
            "error_code": "500",
            "error_title": "Internal Control Unit Fault",
            "error_message": (
                "An unexpected condition occurred while processing your request. "
                "No sensitive details were exposed and our telemetry has logged the event."
            ),
        },
        status=500,
    )
