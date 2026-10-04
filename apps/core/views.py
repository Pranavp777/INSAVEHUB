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
            "question": "How do I preview and download Instagram Videos or Reels in 1080p?",
            "answer": (
                "Paste any public Instagram Reel, Video, or Post URL into the downloader box, "
                "click Analyze, use the built-in Video Preview player, and tap Download MP4."
            ),
        },
        {
            "question": "Can I watch a video preview before downloading?",
            "answer": (
                "Yes. Every analyzed Instagram Reel or Video includes an instant HD video preview "
                "player with audio and fullscreen controls before you save the file."
            ),
        },
        {
            "question": "Is INSTASAVE HUB free and does it require login?",
            "answer": (
                "INSTASAVE HUB is free to use and never requires your Instagram login. "
                "All public Reels, Videos, Photos, Carousels, and Profile Avatars are supported."
            ),
        },
        {
            "question": "Does it work on iPhone, Android, Mac, and Windows?",
            "answer": (
                "Yes. Works in any modern browser and can be installed as a standalone app "
                "via the Install App button."
            ),
        },
    ]

    context = {
        "page_title": "INSTASAVE HUB — Free Instagram Video, Reel & Photo Downloader (1080p HD)",
        "meta_description": (
            "Download Instagram Videos, Reels, Photos, Carousels, and Profile Pictures in original "
            "1080p Full HD MP4 & JPG with live video preview. Fast, free, no login required."
        ),
        "meta_keywords": (
            "instagram video downloader, instagram reel downloader, download instagram reels, "
            "instagram photo downloader, instasave hub, save instagram video 1080p, ig video preview, "
            "instagram carousel downloader, instagram post downloader, free ig downloader"
        ),
        "tools": tools,
        "preset_amounts": config.get_preset_amounts_list(),
        "faqs": faqs,
    }
    return render(request, "home.html", context)


def robots_txt(request: HttpRequest) -> HttpResponse:
    """
    Serve robots.txt for search engine crawlers and AdSense verification bots.
    Explicitly permits Googlebot, Mediapartners-Google (Google AdSense crawler),
    Google-Display-Ads-Bot, and general crawlers to index public pages, ads.txt,
    and sitemap.xml while keeping admin and private API endpoints disallow-listed.
    """
    base_url = getattr(settings, "CANONICAL_BASE_URL", "http://localhost:8000").rstrip("/")
    lines = [
        "User-agent: Mediapartners-Google",
        "Allow: /",
        "",
        "User-agent: Googlebot",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /api/",
        "Disallow: /dashboard/",
        "",
        "User-agent: Google-Display-Ads-Bot",
        "Allow: /",
        "",
        "User-agent: *",
        "Allow: /",
        "Allow: /tools/",
        "Allow: /downloads/",
        "Allow: /about/",
        "Allow: /contact/",
        "Allow: /privacy/",
        "Allow: /terms/",
        "Allow: /disclaimer/",
        "Allow: /ads.txt",
        "Allow: /sitemap.xml",
        "Disallow: /admin/",
        "Disallow: /api/",
        "Disallow: /dashboard/",
        "",
        f"Sitemap: {base_url}/sitemap.xml",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")


def ads_txt(request: HttpRequest) -> HttpResponse:
    """
    Serve dynamic ads.txt for Google AdSense verification.
    Generates the official 'google.com, pub-XXXXXXXXXXXXXXXX, DIRECT, f08c47fec0942fa0'
    entry from the configured ADSENSE_PUBLISHER_ID.
    """
    config = SiteConfiguration.get_solo()
    pub_id = config.get_adsense_publisher_id()

    if not pub_id:
        body = (
            "# Google AdSense ads.txt for INSTASAVE HUB\n"
            "# Configure ADSENSE_PUBLISHER_ID in environment or Django Admin to publish your publisher ID.\n"
        )
    else:
        body = f"google.com, {pub_id}, DIRECT, f08c47fec0942fa0\n"

    return HttpResponse(body, content_type="text/plain; charset=utf-8")


def sitemap_xml(request: HttpRequest) -> HttpResponse:
    """
    Serve dynamic XML sitemap covering all public tools, downloader endpoints,
    and required informational/legal pages for Google Search Console and crawlers.
    """
    ensure_default_tools()
    base_url = getattr(settings, "CANONICAL_BASE_URL", "http://localhost:8000").rstrip("/")
    now_iso = timezone.now().strftime("%Y-%m-%d")

    # Static public routes with respective changefreq and crawl priorities
    public_routes = [
        (reverse("core:home"), "daily", "1.0"),
        (reverse("downloads:interface"), "weekly", "0.9"),
        (reverse("downloads:tools_list"), "weekly", "0.9"),
        (reverse("core:about"), "monthly", "0.8"),
        (reverse("core:contact"), "monthly", "0.8"),
        (reverse("core:privacy"), "monthly", "0.7"),
        (reverse("core:terms"), "monthly", "0.7"),
        (reverse("core:disclaimer"), "monthly", "0.7"),
        (reverse("donations:index"), "monthly", "0.6"),
    ]

    urls_xml = []
    for path, changefreq, priority in public_routes:
        urls_xml.append(
            f"  <url>\n"
            f"    <loc>{base_url}{path}</loc>\n"
            f"    <lastmod>{now_iso}</lastmod>\n"
            f"    <changefreq>{changefreq}</changefreq>\n"
            f"    <priority>{priority}</priority>\n"
            f"  </url>"
        )

    for tool in Tool.objects.filter(is_active=True).order_by("display_order"):
        tool_path = reverse("downloads:tool_detail", kwargs={"slug": tool.slug})
        urls_xml.append(
            f"  <url>\n"
            f"    <loc>{base_url}{tool_path}</loc>\n"
            f"    <lastmod>{now_iso}</lastmod>\n"
            f"    <changefreq>weekly</changefreq>\n"
            f"    <priority>0.8</priority>\n"
            f"  </url>"
        )

    xml_body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls_xml)
        + "\n</urlset>"
    )
    return HttpResponse(xml_body, content_type="application/xml; charset=utf-8")


def about_view(request: HttpRequest) -> HttpResponse:
    """Render the About Us informational page."""
    return render(
        request,
        "pages/about.html",
        {
            "page_title": "About Us | INSTASAVE HUB",
            "meta_description": (
                "Learn about INSTASAVE HUB's mission, high-performance media delivery architecture, "
                "privacy-first principles, and independent technology."
            ),
        },
    )


def contact_view(request: HttpRequest) -> HttpResponse:
    """Render the Contact Us page and handle user inquiries."""
    from django.contrib import messages
    from django.core.mail import send_mail

    submitted = False
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip()
        subject = request.POST.get("subject", "").strip() or "General Inquiry"
        message_text = request.POST.get("message", "").strip()

        if not name or not email or not message_text:
            messages.error(request, "Please fill in all required fields (Name, Email, and Message).")
        else:
            try:
                send_mail(
                    subject=f"[INSTASAVE HUB Contact] {subject} from {name}",
                    message=f"Name: {name}\nEmail: {email}\n\nMessage:\n{message_text}",
                    from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@insavehub.com"),
                    recipient_list=[getattr(settings, "DEFAULT_FROM_EMAIL", "support@insavehub.com")],
                    fail_silently=True,
                )
            except Exception:
                pass
            messages.success(
                request,
                "Thank you for reaching out! Your message has been received and our team will review it shortly.",
            )
            submitted = True

    return render(
        request,
        "pages/contact.html",
        {
            "page_title": "Contact Us | INSTASAVE HUB",
            "meta_description": (
                "Have questions, feedback, or DMCA inquiries? Contact the INSTASAVE HUB team "
                "for technical assistance and support."
            ),
            "submitted": submitted,
        },
    )


def privacy_view(request: HttpRequest) -> HttpResponse:
    """Render the comprehensive Privacy Policy page compliant with GDPR, CCPA, and Google AdSense."""
    return render(
        request,
        "pages/privacy.html",
        {
            "page_title": "Privacy Policy | INSTASAVE HUB",
            "meta_description": (
                "Review INSTASAVE HUB's Privacy Policy. Learn about our zero-retention media routing, "
                "cookie policies, Google AdSense compliance, and user data rights."
            ),
        },
    )


def terms_view(request: HttpRequest) -> HttpResponse:
    """Render the Terms & Conditions and Acceptable Use Policy."""
    return render(
        request,
        "pages/terms.html",
        {
            "page_title": "Terms & Conditions | INSTASAVE HUB",
            "meta_description": (
                "Review the Terms and Conditions of INSTASAVE HUB. Understand acceptable use, "
                "copyright compliance, intellectual property disclaimers, and user obligations."
            ),
        },
    )


def disclaimer_view(request: HttpRequest) -> HttpResponse:
    """Render the Legal Disclaimer and Non-Affiliation Notice."""
    return render(
        request,
        "pages/disclaimer.html",
        {
            "page_title": "Legal Disclaimer | INSTASAVE HUB",
            "meta_description": (
                "Official legal disclaimer for INSTASAVE HUB: independent utility status, "
                "non-affiliation with Meta Platforms and Instagram, and copyright compliance notice."
            ),
        },
    )


def health_check(request: HttpRequest) -> JsonResponse:
    """Edge health probe endpoint for Cloudflare Workers and uptime monitors."""
    return JsonResponse(
        {
            "status": "operational",
            "service": "instasave-hub",
            "timestamp": timezone.now().isoformat(),
        }
    )


def offline_view(request: HttpRequest) -> HttpResponse:
    """Render the PWA offline fallback page when device network connection is unavailable."""
    return render(
        request,
        "offline.html",
        {
            "page_title": "Offline Mode | INSTASAVE HUB",
            "meta_description": "You are currently offline. Check your network connection to access INSTASAVE HUB.",
        },
    )


def web_manifest(request: HttpRequest) -> JsonResponse:
    """
    Serve the Progressive Web App (PWA) manifest for desktop and mobile installation.
    Uses dynamic settings configured in SiteConfiguration (Admin & Environment).
    """
    config = SiteConfiguration.get_solo()
    manifest = config.get_pwa_manifest()
    response = JsonResponse(
        manifest,
        content_type="application/manifest+json; charset=utf-8",
    )
    response["Cache-Control"] = "public, max-age=3600"
    return response


def service_worker(request: HttpRequest) -> HttpResponse:
    """
    Serve the root-scoped Service Worker for PWA installability, app shell caching,
    and reliable offline handling while strictly safeguarding user auth and sensitive routes.
    """
    sw_script = """const CACHE_NAME = 'instasavehub-pwa-v5';
const OFFLINE_URL = '/offline/';

const PRECACHE_ASSETS = [
  '/',
  '/offline/',
  '/static/css/tokens.css',
  '/static/css/glass-orbit.css',
  '/static/css/components.css',
  '/static/css/responsive.css',
  '/static/images/logo.png',
  '/static/images/icon-192.png',
  '/static/images/icon-512.png',
  '/static/js/pwa-install.js',
  '/static/js/orbit-engine.js'
];

const EXCLUDED_PATTERNS = [
  /\\/admin\\//,
  /\\/auth\\//,
  /\\/donations\\//,
  /\\/donate\\//,
  /\\/payment\\//,
  /\\/api\\//,
  /pagead2\\.googlesyndication\\.com/,
  /doubleclick\\.net/,
  /google-analytics\\.com/,
  /googletagmanager\\.com/,
  /checkout\\.razorpay\\.com/,
  /api\\.razorpay\\.com/
];

function isExcluded(urlStr) {
  return EXCLUDED_PATTERNS.some((pattern) => pattern.test(urlStr));
}

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(PRECACHE_ASSETS).catch((err) => {
        console.warn('[PWA SW] Precache warning:', err);
      });
    })
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => {
          return caches.delete(k);
        })
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;

  const url = new URL(event.request.url);

  // Strictly avoid caching admin, auth, payment, API, and ad networks
  if (isExcluded(event.request.url) || isExcluded(url.pathname)) {
    return;
  }

  // Navigation requests: HTML pages (Network-first with offline fallback)
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request)
        .then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const responseClone = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, responseClone));
          }
          return networkResponse;
        })
        .catch(async () => {
          const cached = await caches.match(event.request);
          if (cached) return cached;
          const offlinePage = await caches.match(OFFLINE_URL);
          if (offlinePage) return offlinePage;
          return new Response(
            '<!DOCTYPE html><html><head><title>Offline</title><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"></head><body style=\"background:#030712;color:#f8fafc;font-family:sans-serif;text-align:center;padding:50px;\"><h1>You are offline</h1><p>Please check your connection and reload.</p></body></html>',
            { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
          );
        })
    );
    return;
  }

  // Static Assets (Cache-First with Background Revalidation)
  if (url.origin === self.location.origin && url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then((cachedResponse) => {
        const fetchPromise = fetch(event.request)
          .then((networkResponse) => {
            if (networkResponse && networkResponse.status === 200) {
              const responseClone = networkResponse.clone();
              caches.open(CACHE_NAME).then((cache) => cache.put(event.request, responseClone));
            }
            return networkResponse;
          })
          .catch(() => null);

        return cachedResponse || fetchPromise;
      })
    );
  }
});
"""
    response = HttpResponse(sw_script, content_type="application/javascript; charset=utf-8")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
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
