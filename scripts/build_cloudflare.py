"""
Cloudflare Pages & Workers build script invoked by `npm run build`.
Works in both full SQLite/PostgreSQL environments and Cloudflare's build image
where Python is compiled without the `_sqlite3` C extension.
"""
import json
import os
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Check whether Python's _sqlite3 C extension is available in this build container
try:
    import _sqlite3  # noqa: F401

    HAS_SQLITE3 = True
except ImportError:
    HAS_SQLITE3 = False

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DJANGO_ENV", "development")

import django  # noqa: E402
from django.conf import settings  # noqa: E402


def _configure_dummy_db_if_needed() -> None:
    """Switch DATABASES to django.db.backends.dummy if _sqlite3 is unavailable."""
    if not HAS_SQLITE3:
        settings.DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.dummy",
            }
        }


def _build_tool_objects():
    """Construct in-memory Tool objects matching DEFAULT_TOOLS for template rendering."""
    from apps.downloads.services import DEFAULT_TOOLS

    category_labels = {
        "reel": "Reel Utility",
        "video": "Video Utility",
        "image": "Image Utility",
        "post": "Public Post Utility",
        "profile": "Profile Media Utility",
        "metadata": "Content Information Extractor",
    }
    tools = []
    for idx, item in enumerate(DEFAULT_TOOLS, start=1):
        cat = str(item["category"])
        cat_label = category_labels.get(cat, "Instagram Utility")
        tools.append(
            SimpleNamespace(
                pk=idx,
                id=idx,
                name=item["name"],
                slug=item["slug"],
                category=cat,
                short_description=item["short_description"],
                detailed_description=item["detailed_description"],
                supported_url_hint=item["supported_url_hint"],
                output_formats=item["output_formats"],
                badge_code=item["badge_code"],
                is_active=True,
                is_featured=True,
                display_order=item["display_order"],
                total_uses=0,
                get_category_display=lambda label=cat_label: label,
            )
        )
    return tools


def _render_without_db(dist_dir: Path) -> None:
    """Render all application templates into dist_dir without requiring _sqlite3."""
    from django.template.loader import render_to_string
    from django.test import RequestFactory
    from apps.core.views import robots_txt, service_worker, web_manifest

    rf = RequestFactory()
    tools = _build_tool_objects()

    site_config = SimpleNamespace(
        platform_name="INSTASAVE HUB",
        tagline="Precision Instagram Media & Content Control Center",
        support_email="support@insavehub.example.com",
        enable_advertisements=True,
        ad_countdown_seconds=30,
        free_access_hours=24,
        free_downloads_before_ad=1,
        enable_donations=True,
        donation_currency="INR",
        donation_preset_amounts="100,250,500,1000",
        minimum_donation_amount=50,
        maximum_donation_amount=50000,
        enable_google_oauth=True,
        enable_guest_downloads=True,
        maintenance_mode=False,
    )
    access_state = {
        "state": "STATE_1",
        "mode": "initial_free",
        "label": "Free Download Ready",
        "sublabel": "Direct 1080p high-speed download ready",
        "has_free_24h": False,
        "free_24h_expires_at": None,
        "free_24h_remaining_seconds": 0,
        "free_24h_formatted": "00:00:00",
        "ad_required": False,
        "initial_5s_ad_required": False,
        "first_download_completed": False,
        "can_download_immediately": True,
        "completed_in_cycle": 0,
        "free_allowance": 1,
        "active_ad_session_id": None,
        "active_ad_remaining_seconds": 0,
    }
    anon_user = SimpleNamespace(is_authenticated=False, is_staff=False, is_superuser=False, username="")

    def make_ctx(path: str, extra: dict) -> dict:
        req = rf.get(path, HTTP_HOST="insavehub.workers.dev")
        req.user = anon_user
        req.session = {}
        base_ctx = {
            "request": req,
            "user": anon_user,
            "site_config": site_config,
            "access_state": access_state,
            "canonical_base_url": "https://insavehub.workers.dev",
            "google_oauth_enabled": True,
            "messages": [],
            "csrf_token": "cloudflare-edge-csrf-token",
        }
        base_ctx.update(extra)
        return base_ctx

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

    dummy_ad_session = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001",
        ad_type="unlock_30s",
        nonce_token="edge-ad-nonce-token",
        remaining_seconds=30,
        required_duration_seconds=30,
        pending_download=None,
    )

    pages = [
        (
            "/",
            "index.html",
            "home.html",
            {
                "page_title": "INSTASAVE HUB — Free Instagram Video, Reel & Photo Downloader (1080p HD)",
                "meta_description": (
                    "Download Instagram Videos, Reels, Photos, Carousels, and Profile Pictures in original "
                    "1080p Full HD MP4 & JPG with live video preview. Fast, free, no login required."
                ),
                "meta_keywords": (
                    "instagram video downloader, instagram reel downloader, download instagram reels, "
                    "instagram photo downloader, instasave hub, save instagram video 1080p, ig video preview"
                ),
                "tools": tools,
                "preset_amounts": [100, 250, 500, 1000],
                "faqs": faqs,
            },
        ),
        (
            "/tools/",
            "tools/index.html",
            "tools/index.html",
            {
                "page_title": "Instagram Video, Reel, Photo & Post Downloader Tools | INSTASAVE HUB",
                "meta_description": (
                    "Free Instagram Downloader tools to preview and save Instagram Reels, Videos, "
                    "Photos, Carousels, and HD Profile Pictures in 1080p MP4 & JPG."
                ),
                "tools": tools,
            },
        ),
        (
            "/downloads/",
            "downloads/index.html",
            "downloads/interface.html",
            {
                "page_title": "Instagram Video & Reel Downloader with Live Preview | INSTASAVE HUB",
                "meta_description": (
                    "Paste any public Instagram URL to preview videos in 1080p HD and download "
                    "Instagram Reels, Videos, Photos, and Carousels instantly."
                ),
                "tools": tools,
                "selected_tool_slug": "",
                "prefill_url": "",
                "recent_downloads": [],
            },
        ),
        (
            "/downloads/history/",
            "downloads/history/index.html",
            "downloads/history.html",
            {
                "page_title": "Download History | INSTASAVE HUB",
                "meta_description": "Review your analyzed Instagram content and completed downloads.",
                "downloads": [],
            },
        ),
        (
            "/about/",
            "about/index.html",
            "pages/about.html",
            {
                "page_title": "About Us | INSTASAVE HUB",
                "meta_description": "About INSTASAVE HUB - High-speed zero-retention Instagram downloader.",
            },
        ),
        (
            "/contact/",
            "contact/index.html",
            "pages/contact.html",
            {
                "page_title": "Contact Us | INSTASAVE HUB",
                "meta_description": "Contact INSTASAVE HUB technical support and inquiries.",
            },
        ),
        (
            "/privacy/",
            "privacy/index.html",
            "pages/privacy.html",
            {
                "page_title": "Privacy Policy | INSTASAVE HUB",
                "meta_description": "Privacy Policy and Google AdSense compliance for INSTASAVE HUB.",
            },
        ),
        (
            "/terms/",
            "terms/index.html",
            "pages/terms.html",
            {
                "page_title": "Terms & Conditions | INSTASAVE HUB",
                "meta_description": "Terms and conditions of use for INSTASAVE HUB.",
            },
        ),
        (
            "/disclaimer/",
            "disclaimer/index.html",
            "pages/disclaimer.html",
            {
                "page_title": "Legal Disclaimer | INSTASAVE HUB",
                "meta_description": "Legal disclaimer and trademark notice for INSTASAVE HUB.",
            },
        ),
        (
            "/donations/",
            "donations/index.html",
            "donations/index.html",
            {
                "page_title": "Buy Us Coffee | INSTASAVE HUB",
                "meta_description": "Buy Us Coffee on INSTASAVE HUB.",
                "preset_amounts": [100, 250, 500, 1000],
                "currency": "INR",
                "recent_donations": [],
            },
        ),
        (
            "/auth/login/",
            "auth/login/index.html",
            "auth/login.html",
            {
                "page_title": "Sign In | INSTASAVE HUB",
            },
        ),
        (
            "/auth/register/",
            "auth/register/index.html",
            "auth/register.html",
            {
                "page_title": "Register | INSTASAVE HUB",
            },
        ),
        (
            "/404/",
            "404.html",
            "errors/404.html",
            {
                "error_code": "404",
                "error_title": "Requested Coordinate Not Found",
                "error_message": "The page you requested does not exist at this address.",
            },
        ),
    ]

    for tool in tools:
        other_tools = [t for t in tools if t.slug != tool.slug]
        pages.append(
            (
                f"/tools/{tool.slug}/",
                f"tools/{tool.slug}/index.html",
                "tools/tool_detail.html",
                {
                    "page_title": f"{tool.name} — Free 1080p HD Preview & Download | INSTASAVE HUB",
                    "meta_description": f"{tool.short_description} Live video preview and fast 1080p download on INSTASAVE HUB.",
                    "tool": tool,
                    "other_tools": other_tools,
                },
            )
        )

    for route_path, target_rel, tpl_name, extra_ctx in pages:
        html_str = render_to_string(tpl_name, make_ctx(route_path, extra_ctx))
        out_file = dist_dir / target_rel
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(html_str, encoding="utf-8")
        print(f"[INSTASAVE HUB Build] Rendered {route_path} -> dist/{target_rel}")

    req_root = rf.get("/")
    (dist_dir / "manifest.webmanifest").write_bytes(web_manifest(req_root).content)
    (dist_dir / "sw.js").write_bytes(service_worker(req_root).content)
    (dist_dir / "robots.txt").write_bytes(robots_txt(req_root).content)

    pub_id = getattr(settings, "ADSENSE_PUBLISHER_ID", "").strip()
    if pub_id:
        import re
        clean_pub = re.sub(r"^ca-", "", pub_id, flags=re.IGNORECASE).strip()
        if not clean_pub.lower().startswith("pub-"):
            clean_pub = f"pub-{clean_pub}"
        ads_txt_body = f"google.com, {clean_pub}, DIRECT, f08c47fec0942fa0\n"
    else:
        ads_txt_body = "# Google AdSense ads.txt for INSTASAVE HUB\n# Set ADSENSE_PUBLISHER_ID environment variable to configure your publisher ID.\n"
    (dist_dir / "ads.txt").write_text(ads_txt_body, encoding="utf-8")

    tool_sitemap_entries = "\n".join(
        f"  <url><loc>https://insavehub.workers.dev/tools/{t.slug}/</loc><changefreq>weekly</changefreq><priority>0.8</priority></url>"
        for t in tools
    )
    sitemap_xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://insavehub.workers.dev/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>
  <url><loc>https://insavehub.workers.dev/downloads/</loc><changefreq>weekly</changefreq><priority>0.9</priority></url>
  <url><loc>https://insavehub.workers.dev/tools/</loc><changefreq>weekly</changefreq><priority>0.9</priority></url>
{tool_sitemap_entries}
  <url><loc>https://insavehub.workers.dev/about/</loc><changefreq>monthly</changefreq><priority>0.8</priority></url>
  <url><loc>https://insavehub.workers.dev/contact/</loc><changefreq>monthly</changefreq><priority>0.8</priority></url>
  <url><loc>https://insavehub.workers.dev/privacy/</loc><changefreq>monthly</changefreq><priority>0.7</priority></url>
  <url><loc>https://insavehub.workers.dev/terms/</loc><changefreq>monthly</changefreq><priority>0.7</priority></url>
  <url><loc>https://insavehub.workers.dev/disclaimer/</loc><changefreq>monthly</changefreq><priority>0.7</priority></url>
  <url><loc>https://insavehub.workers.dev/donations/</loc><changefreq>monthly</changefreq><priority>0.6</priority></url>
</urlset>"""
    (dist_dir / "sitemap.xml").write_text(sitemap_xml_content, encoding="utf-8")


def main() -> None:
    print(f"[INSTASAVE HUB Build] Initializing Django (HAS_SQLITE3={HAS_SQLITE3})...")
    _configure_dummy_db_if_needed()
    django.setup()

    dist_dir = BASE_DIR / "dist"
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    dist_dir.mkdir(parents=True, exist_ok=True)

    # Copy static assets directly into dist/static/ and ./staticfiles/
    static_src = BASE_DIR / "static"
    staticfiles_dir = BASE_DIR / "staticfiles"
    if staticfiles_dir.exists():
        shutil.rmtree(staticfiles_dir)
    def _copy_safe(src: Path, dst: Path) -> None:
        for root, _dirs, files in os.walk(src):
            rel = Path(root).relative_to(src)
            t_dir = dst / rel
            t_dir.mkdir(parents=True, exist_ok=True)
            for f in files:
                s_file = Path(root) / f
                d_file = t_dir / f
                try:
                    d_file.write_bytes(s_file.read_bytes())
                except Exception:
                    pass

    _copy_safe(static_src, staticfiles_dir)
    _copy_safe(static_src, dist_dir / "static")

    if HAS_SQLITE3:
        from django.core.management import call_command
        from django.test import Client
        from apps.downloads.models import Tool
        from apps.downloads.services import ensure_default_tools

        call_command("migrate", interactive=False, verbosity=0)
        call_command("collectstatic", interactive=False, clear=True, verbosity=0)
        _copy_safe(staticfiles_dir, dist_dir / "static")
        ensure_default_tools()

        client = Client(HTTP_HOST="localhost")
        routes = [
            ("/", "index.html"),
            ("/tools/", "tools/index.html"),
            ("/downloads/", "downloads/index.html"),
            ("/downloads/history/", "downloads/history/index.html"),
            ("/about/", "about/index.html"),
            ("/contact/", "contact/index.html"),
            ("/privacy/", "privacy/index.html"),
            ("/terms/", "terms/index.html"),
            ("/disclaimer/", "disclaimer/index.html"),
            ("/donations/", "donations/index.html"),
            ("/auth/login/", "auth/login/index.html"),
            ("/auth/register/", "auth/register/index.html"),
            ("/manifest.webmanifest", "manifest.webmanifest"),
            ("/sw.js", "sw.js"),
            ("/robots.txt", "robots.txt"),
            ("/ads.txt", "ads.txt"),
            ("/sitemap.xml", "sitemap.xml"),
        ]
        for tool in Tool.objects.filter(is_active=True):
            routes.append((f"/tools/{tool.slug}/", f"tools/{tool.slug}/index.html"))

        for route_path, target_rel in routes:
            resp = client.get(route_path)
            if resp.status_code == 200:
                out_file = dist_dir / target_rel
                out_file.parent.mkdir(parents=True, exist_ok=True)
                out_file.write_bytes(resp.content)
                print(f"[INSTASAVE HUB Build] Rendered {route_path} -> dist/{target_rel}")

        from django.test import override_settings
        with override_settings(DEBUG=False):
            resp_404 = client.get("/non-existent-route-404-preview/")
            (dist_dir / "404.html").write_bytes(resp_404.content)
    else:
        _render_without_db(dist_dir)

    for alias in ("public", "build"):
        alias_dir = BASE_DIR / alias
        if alias_dir.exists():
            shutil.rmtree(alias_dir)
        shutil.copytree(dist_dir, alias_dir)

    print("[INSTASAVE HUB Build] Build completed successfully.")


if __name__ == "__main__":
    main()
