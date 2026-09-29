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
