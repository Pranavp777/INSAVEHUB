"""Tests for Rate Limiting, Landing Page, SEO endpoints (robots.txt, sitemap.xml), and Security Headers."""
import json

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.core.models import SiteConfiguration


class CoreRateLimitAndSEOTests(TestCase):
    def setUp(self) -> None:
        cache.clear()

    def test_landing_page_robots_and_sitemap(self) -> None:
        home_resp = self.client.get(reverse("core:home"))
        self.assertEqual(home_resp.status_code, 200)
        self.assertContains(home_resp, "INSTASAVE HUB")
        self.assertContains(home_resp, "resVideoPlayer")
        self.assertContains(home_resp, "Preview Video")
        self.assertContains(home_resp, "FAQPage")
        self.assertContains(home_resp, "HowTo")
        self.assertIn("Content-Security-Policy", home_resp)

        robots_resp = self.client.get(reverse("core:robots_txt"))
        self.assertEqual(robots_resp.status_code, 200)
        self.assertIn("Sitemap:", robots_resp.content.decode("utf-8"))

        sitemap_resp = self.client.get(reverse("core:sitemap_xml"))
        self.assertEqual(sitemap_resp.status_code, 200)
        self.assertIn("<urlset", sitemap_resp.content.decode("utf-8"))

    def test_configurable_rate_limiting_returns_friendly_429(self) -> None:
        config = SiteConfiguration.get_solo()
        config.rate_limit_analyze_per_min = 2
        config.save()

        url = reverse("downloads:analyze_api")
        payload = json.dumps({"url": "https://www.instagram.com/reel/RateLimit01/"})

        # First 2 requests are allowed
        r1 = self.client.post(
            url, data=payload, content_type="application/json", HTTP_ACCEPT="application/json"
        )
        self.assertEqual(r1.status_code, 200)

        r2 = self.client.post(
            url, data=payload, content_type="application/json", HTTP_ACCEPT="application/json"
        )
        self.assertEqual(r2.status_code, 200)

        # 3rd request within the same minute window triggers HTTP 429
        r3 = self.client.post(
            url, data=payload, content_type="application/json", HTTP_ACCEPT="application/json"
        )
        self.assertEqual(r3.status_code, 429)
        self.assertEqual(r3.json()["code"], "rate_limit_exceeded")
        self.assertIn("Retry-After", r3)

    def test_pwa_web_manifest_endpoints(self) -> None:
        """Verify /manifest.json and /manifest.webmanifest endpoints return valid W3C PWA manifests."""
        for url in ["/manifest.json", "/manifest.webmanifest"]:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200)
            self.assertIn("application/manifest+json", resp["Content-Type"])

            data = resp.json()
            self.assertEqual(data["display"], "standalone")
            self.assertEqual(data["orientation"], "any")
            self.assertIn("name", data)
            self.assertIn("short_name", data)
            self.assertIn("start_url", data)
            self.assertIn("theme_color", data)
            self.assertIn("background_color", data)
            self.assertTrue(len(data["icons"]) >= 2)

            sizes = [icon["sizes"] for icon in data["icons"]]
            self.assertIn("192x192", sizes)
            self.assertIn("512x512", sizes)

            purposes = [icon.get("purpose") for icon in data["icons"]]
            self.assertIn("maskable", purposes)

    def test_pwa_service_worker_endpoints(self) -> None:
        """Verify /service-worker.js and /sw.js are served with valid headers and offline logic."""
        for url in ["/service-worker.js", "/sw.js"]:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200)
            self.assertIn("javascript", resp["Content-Type"])
            self.assertEqual(resp.get("Service-Worker-Allowed"), "/")
            content = resp.content.decode("utf-8")
            self.assertIn("CACHE_NAME", content)
            self.assertIn("/offline/", content)
            self.assertIn("EXCLUDED_PATTERNS", content)
            self.assertIn("admin", content)
            self.assertIn("auth", content)

    def test_pwa_offline_page(self) -> None:
        """Verify /offline/ route renders informative glass offline page with retry controls."""
        resp = self.client.get("/offline/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Offline")
        self.assertContains(resp, "Retry Connection")
        self.assertContains(resp, "offlineNoticeBanner")

    def test_pwa_configuration_customization(self) -> None:
        """Verify that updating PWA settings in SiteConfiguration dynamically updates manifest and UI."""
        config = SiteConfiguration.get_solo()
        config.pwa_name = "Custom Instagram Downloader Suite"
        config.pwa_short_name = "CustomSave"
        config.pwa_install_button_text = "Download App Now"
        config.pwa_theme_color = "#0B1528"
        config.pwa_background_color = "#050B18"
        config.save()

        manifest_resp = self.client.get("/manifest.json")
        self.assertEqual(manifest_resp.status_code, 200)
        data = manifest_resp.json()
        self.assertEqual(data["name"], "Custom Instagram Downloader Suite")
        self.assertEqual(data["short_name"], "CustomSave")
        self.assertEqual(data["theme_color"], "#0B1528")
        self.assertEqual(data["background_color"], "#050B18")

        home_resp = self.client.get(reverse("core:home"))
        self.assertContains(home_resp, "Download App Now")
        self.assertContains(home_resp, "pwa-installed")
        self.assertContains(home_resp, "/manifest.json")
        self.assertContains(home_resp, "/static/js/pwa-install.js")

    def test_all_public_legal_pages_availability(self) -> None:
        """Verify that all essential informational, legal, and compliance pages return HTTP 200."""
        routes_to_test = [
            ("/", "INSTASAVE HUB"),
            ("/about/", "About INSTASAVE HUB"),
            ("/contact/", "Contact Us"),
            ("/privacy/", "Privacy Policy"),
            ("/privacy-policy/", "Privacy Policy"),
            ("/terms/", "Terms &amp; Conditions"),
            ("/terms-of-service/", "Terms &amp; Conditions"),
            ("/terms-and-conditions/", "Terms &amp; Conditions"),
            ("/disclaimer/", "Disclaimer"),
            ("/dmca/", "DMCA &amp; Copyright Policy"),
            ("/faq/", "Frequently Asked Questions"),
            ("/editorial-standards/", "Editorial &amp; Publishing Standards"),
            ("/status/", "Platform Status"),
            ("/guides/", "Knowledge Hub"),
            ("/guides/instagram-video-specs/", "Instagram Video Specifications Guide"),
            ("/guides/troubleshoot-blurry-videos/", "Why Instagram Compresses Videos"),
            ("/guides/reels-vs-stories-vs-posts/", "Reels vs Stories vs Posts"),
            ("/guides/fair-use-copyright-guide/", "Fair Use, Copyright"),
        ]
        for url, expected_text in routes_to_test:
            resp = self.client.get(url, HTTP_HOST="insavehub.com")
            self.assertEqual(resp.status_code, 200, f"Route {url} failed with status {resp.status_code}")
            self.assertContains(resp, expected_text, msg_prefix=f"Route {url} missing expected text: {expected_text}")

    def test_educational_guides_schema_and_technical_content(self) -> None:
        """Verify educational guide pages render structured TechArticle schema and technical tables."""
        for guide_slug in [
            "instagram-video-specs",
            "troubleshoot-blurry-videos",
            "reels-vs-stories-vs-posts",
            "fair-use-copyright-guide",
        ]:
            resp = self.client.get(f"/guides/{guide_slug}/", HTTP_HOST="insavehub.com")
            self.assertEqual(resp.status_code, 200)
            self.assertContains(resp, "TechArticle")
            self.assertContains(resp, "INSTASAVE HUB")

        # Test editorial standards page
        ed_resp = self.client.get("/editorial-standards/", HTTP_HOST="insavehub.com")
        self.assertEqual(ed_resp.status_code, 200)
        self.assertContains(ed_resp, "Zero-Retention Security &amp; Privacy Audits")
        self.assertContains(ed_resp, "Mobile Safari")

        # Test platform status page
        st_resp = self.client.get("/status/", HTTP_HOST="insavehub.com")
        self.assertEqual(st_resp.status_code, 200)
        self.assertContains(st_resp, "Structural Maintenance Changelog")
        self.assertContains(st_resp, "v2.4.2")

    def test_ads_txt_default_and_custom_publisher_id(self) -> None:
        """Verify /ads.txt serves official publisher ID and never an empty comment."""
        resp = self.client.get("/ads.txt")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("google.com", resp.content.decode("utf-8"))
        self.assertIn("pub-7764836554568456", resp.content.decode("utf-8"))
        self.assertIn("DIRECT, f08c47fec0942fa0", resp.content.decode("utf-8"))

    def test_sitemap_xml_and_robots_txt_contains_all_routes(self) -> None:
        """Verify /sitemap.xml and /robots.txt include all legal and utility routes."""
        sitemap_resp = self.client.get("/sitemap.xml", HTTP_HOST="insavehub.com")
        self.assertEqual(sitemap_resp.status_code, 200)
        sitemap_text = sitemap_resp.content.decode("utf-8")
        self.assertIn("/privacy/", sitemap_text)
        self.assertIn("/privacy-policy/", sitemap_text)
        self.assertIn("/terms/", sitemap_text)
        self.assertIn("/dmca/", sitemap_text)
        self.assertIn("/faq/", sitemap_text)
        self.assertIn("/about/", sitemap_text)
        self.assertIn("/contact/", sitemap_text)
        self.assertIn("/guides/", sitemap_text)
        self.assertIn("/editorial-standards/", sitemap_text)
        self.assertIn("/status/", sitemap_text)
        self.assertNotIn("localhost", sitemap_text)

        robots_resp = self.client.get("/robots.txt", HTTP_HOST="insavehub.com")
        self.assertEqual(robots_resp.status_code, 200)
        robots_text = robots_resp.content.decode("utf-8")
        self.assertIn("User-agent: Mediapartners-Google", robots_text)
        self.assertIn("Allow: /dmca/", robots_text)
        self.assertIn("Allow: /faq/", robots_text)
        self.assertIn("Allow: /privacy-policy/", robots_text)
        self.assertIn("Allow: /guides/", robots_text)
        self.assertIn("Allow: /editorial-standards/", robots_text)
        self.assertNotIn("localhost", robots_text)

    def test_adsense_ad_unit_rendering(self) -> None:
        """Verify AdSense ad unit renders the exact slot 8738112208 and ads 1 comment."""
        resp = self.client.get(reverse("core:home"), HTTP_HOST="insavehub.com")
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        self.assertIn("ca-pub-7764836554568456", content)
        self.assertIn("8738112208", content)
        self.assertIn("<!-- ads 1 -->", content)
        self.assertIn('style="display:inline-block;width:728px;height:90px"', content)
        self.assertIn("ADVERTISEMENT", content)


