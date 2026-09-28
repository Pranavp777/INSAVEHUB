"""
Cloudflare Pages & Workers build script invoked by `npm run build`.
Runs Django database migrations, collects static assets, and pre-renders
all application routes and static assets into ./dist, ./build, and ./public.
"""
import os
import shutil
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DJANGO_ENV", "development")

import django  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.test import Client  # noqa: E402


def main() -> None:
    print("[InSave Hub Build] Initializing Django environment...")
    django.setup()

    print("[InSave Hub Build] Applying database migrations...")
    call_command("migrate", interactive=False, verbosity=1)

    print("[InSave Hub Build] Collecting static files...")
    call_command("collectstatic", interactive=False, clear=True, verbosity=1)

    from apps.downloads.models import Tool
    from apps.downloads.services import ensure_default_tools

    ensure_default_tools()

    dist_dir = BASE_DIR / "dist"
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    dist_dir.mkdir(parents=True, exist_ok=True)

    # Copy static files into dist/static/
    static_src = BASE_DIR / "staticfiles"
    if not static_src.exists():
        static_src = BASE_DIR / "static"
    shutil.copytree(static_src, dist_dir / "static", dirs_exist_ok=True)

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

    # Render 404 page
    resp_404 = client.get("/non-existent-route-404-preview/")
    (dist_dir / "404.html").write_bytes(resp_404.content)

    # Mirror dist to ./public and ./build so any Cloudflare output directory setting works
    for alias in ("public", "build"):
        alias_dir = BASE_DIR / alias
        if alias_dir.exists():
            shutil.rmtree(alias_dir)
        shutil.copytree(dist_dir, alias_dir)

    print("[InSave Hub Build] Build completed successfully.")


if __name__ == "__main__":
    main()
