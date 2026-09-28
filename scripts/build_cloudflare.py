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
        platform_name="InSave Hub",
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
        "mode": "initial_free",
        "label": "Free Access Available",
        "has_free_24h": False,
        "free_24h_expires_at": None,
        "free_24h_remaining_seconds": 0,
        "free_24h_formatted": "00:00:00",
        "ad_required": False,
        "can_download_immediately": True,
        "completed_in_cycle": 0,
        "free_allowance": 1,
        "active_ad_session_id": None,
        "active_ad_remaining_seconds": 30,
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
                "Yes. Click the Install App button in the top navigation bar or hero section to add "
                "InSave Hub to your desktop or mobile home screen."
            ),
        },
    ]

    pages = [
        (
            "/",
            "index.html",
            "home.html",
            {
                "page_title": "InSave Hub | Your Instagram Workflow, Refined.",
                "meta_description": "Fast Instagram Video, Reel, Photo, and Post downloader.",
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
                "page_title": "Instagram Content Utilities | InSave Hub",
                "meta_description": "Explore Instagram utilities for Reels, Videos, Photos, and Posts.",
                "tools": tools,
            },
        ),
        (
            "/downloads/",
            "downloads/index.html",
            "downloads/interface.html",
            {
                "page_title": "Download Control Interface | InSave Hub",
                "meta_description": "Analyze public Instagram URLs and execute high-resolution downloads.",
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
                "page_title": "Download History | InSave Hub",
                "meta_description": "Review your analyzed Instagram content and completed downloads.",
                "downloads": [],
            },
        ),
        (
            "/donations/",
            "donations/index.html",
            "donations/index.html",
            {
                "page_title": "Buy Us Cofee | InSave Hub",
                "meta_description": "Buy Us Cofee on InSave Hub.",
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
                "page_title": "Sign In | InSave Hub",
            },
        ),
        (
            "/auth/register/",
            "auth/register/index.html",
            "auth/register.html",
            {
                "page_title": "Register | InSave Hub",
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
                    "page_title": f"{tool.name} | InSave Hub",
                    "meta_description": tool.short_description,
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
        print(f"[InSave Hub Build] Rendered {route_path} -> dist/{target_rel}")

    req_root = rf.get("/")
    (dist_dir / "manifest.webmanifest").write_bytes(web_manifest(req_root).content)
    (dist_dir / "sw.js").write_bytes(service_worker(req_root).content)
    (dist_dir / "robots.txt").write_bytes(robots_txt(req_root).content)

    sitemap_xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://insavehub.workers.dev/</loc><priority>1.0</priority></url>
  <url><loc>https://insavehub.workers.dev/tools/</loc><priority>0.8</priority></url>
  <url><loc>https://insavehub.workers.dev/downloads/</loc><priority>0.8</priority></url>
  <url><loc>https://insavehub.workers.dev/donations/</loc><priority>0.7</priority></url>
</urlset>"""
    (dist_dir / "sitemap.xml").write_text(sitemap_xml_content, encoding="utf-8")


def main() -> None:
    print(f"[InSave Hub Build] Initializing Django (HAS_SQLITE3={HAS_SQLITE3})...")
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
    shutil.copytree(static_src, staticfiles_dir, dirs_exist_ok=True)
    shutil.copytree(static_src, dist_dir / "static", dirs_exist_ok=True)

    if HAS_SQLITE3:
        from django.core.management import call_command
        from django.test import Client
        from apps.downloads.models import Tool
        from apps.downloads.services import ensure_default_tools

        call_command("migrate", interactive=False, verbosity=0)
        call_command("collectstatic", interactive=False, clear=True, verbosity=0)
        shutil.copytree(staticfiles_dir, dist_dir / "static", dirs_exist_ok=True)
        ensure_default_tools()

        client = Client(HTTP_HOST="localhost")
        routes = [
            ("/", "index.html"),
            ("/tools/", "tools/index.html"),
            ("/downloads/", "downloads/index.html"),
            ("/downloads/history/", "downloads/history/index.html"),
            ("/donations/", "donations/index.html"),
            ("/auth/login/", "auth/login/index.html"),
            ("/auth/register/", "auth/register/index.html"),
            ("/ads/gate/", "ads/gate/index.html"),
            ("/manifest.webmanifest", "manifest.webmanifest"),
            ("/sw.js", "sw.js"),
            ("/robots.txt", "robots.txt"),
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
                print(f"[InSave Hub Build] Rendered {route_path} -> dist/{target_rel}")

        resp_404 = client.get("/non-existent-route-404-preview/")
        (dist_dir / "404.html").write_bytes(resp_404.content)
    else:
        _render_without_db(dist_dir)

    for alias in ("public", "build"):
        alias_dir = BASE_DIR / alias
        if alias_dir.exists():
            shutil.rmtree(alias_dir)
        shutil.copytree(dist_dir, alias_dir)

    print("[InSave Hub Build] Build completed successfully.")


if __name__ == "__main__":
    main()
