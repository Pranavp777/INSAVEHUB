"""Tests for URL analysis, invalid/restricted URLs, download authorization, and download history."""
import json

from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from apps.downloads.models import Download


class DownloadAndValidationTests(TestCase):
    def setUp(self) -> None:
        cache.clear()

    def test_valid_url_analysis_and_download_history(self) -> None:
        resp = self.client.post(
            reverse("downloads:analyze_api"),
            data=json.dumps({"url": "https://www.instagram.com/reel/C8xYz123AbC/"}),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["download"]["shortcode"], "C8xYz123AbC")
        self.assertFalse(payload["access"]["ad_required"])

        # History page displays the analyzed item
        hist_resp = self.client.get(reverse("downloads:history"))
        self.assertEqual(hist_resp.status_code, 200)
        self.assertContains(hist_resp, "C8xYz123AbC")

    def test_invalid_and_restricted_urls_rejected(self) -> None:
        # 1. Non-Instagram domain
        bad_domain = self.client.post(
            reverse("downloads:analyze_api"),
            data=json.dumps({"url": "https://example.com/reel/12345/"}),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(bad_domain.status_code, 400)
        self.assertEqual(bad_domain.json()["code"], "unsupported_domain")

        # 2. Private / restricted stories endpoint
        restricted = self.client.post(
            reverse("downloads:analyze_api"),
            data=json.dumps({"url": "https://www.instagram.com/stories/private_user/12345/"}),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(restricted.status_code, 400)
        self.assertEqual(restricted.json()["code"], "restricted_content")

    def test_unauthorized_cross_session_download_token_rejected(self) -> None:
        # Client A analyzes a URL
        resp = self.client.post(
            reverse("downloads:analyze_api"),
            data=json.dumps({"url": "https://www.instagram.com/p/C9pQr456LmN/"}),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        execute_url = resp.json()["download"]["execute_url"]

        # Client B (different session) attempts to use Client A's download token
        other_client = Client()
        unauth_resp = other_client.get(execute_url, HTTP_ACCEPT="application/json")
        self.assertEqual(unauth_resp.status_code, 403)
        self.assertEqual(unauth_resp.json()["code"], "unauthorized_download")
