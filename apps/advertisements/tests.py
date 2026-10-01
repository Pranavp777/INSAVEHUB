"""
Tests for clean download authorization, AdSession validation,
and safe non-deceptive redirect behavior.
"""
import json
from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.advertisements.models import AdSession, FreeAccessSession
from apps.downloads.models import Download


class AdvertisementAndFreeAccessTests(TestCase):
    def setUp(self) -> None:
        cache.clear()

    def test_direct_unhindered_downloads(self) -> None:
        # 1. First download is allowed immediately without advertisement gates
        r1 = self.client.post(
            reverse("downloads:analyze_api"),
            data=json.dumps({"url": "https://www.instagram.com/reel/FirstReel01/"}),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(r1.status_code, 200)
        self.assertFalse(r1.json()["access"]["ad_required"])
        dl1_exec_url = r1.json()["download"]["execute_url"]

        exec1 = self.client.get(dl1_exec_url)
        self.assertEqual(exec1.status_code, 200)
        self.assertIn("attachment", exec1["Content-Disposition"])

        # 2. Subsequent downloads also proceed directly without deceptive barriers
        r2 = self.client.post(
            reverse("downloads:analyze_api"),
            data=json.dumps({"url": "https://www.instagram.com/reel/SecondReel02/"}),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(r2.status_code, 200)
        self.assertFalse(r2.json()["access"]["ad_required"])
        dl2_exec_url = r2.json()["download"]["execute_url"]

        exec2 = self.client.get(dl2_exec_url)
        self.assertEqual(exec2.status_code, 200)
        self.assertIn("attachment", exec2["Content-Disposition"])

    def test_ad_gate_redirects_safely(self) -> None:
        # Visiting /ads/gate/ redirects cleanly to the downloader interface
        gate_resp = self.client.get(reverse("advertisements:gate"))
        self.assertEqual(gate_resp.status_code, 302)
        self.assertIn(reverse("downloads:interface"), gate_resp["Location"])

    def test_ad_session_timing_and_completion_security(self) -> None:
        self.client.get(reverse("downloads:interface"))
        session_key = self.client.session.session_key or ""
        now = timezone.now()
        ad_session = AdSession.objects.create(
            session_key=session_key,
            ip_hash="testhash",
            ad_type=AdSession.AdType.UNLOCK_30S,
            required_duration_seconds=30,
            started_at=now,
            eligible_at=now + timedelta(seconds=30),
            status=AdSession.Status.ACTIVE,
        )

        early_complete = self.client.post(
            reverse("advertisements:complete"),
            data=json.dumps(
                {
                    "ad_session_id": str(ad_session.id),
                    "nonce_token": ad_session.nonce_token,
                }
            ),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(early_complete.status_code, 403)
        self.assertEqual(early_complete.json()["code"], "ad_countdown_incomplete")

        # Simulate time elapsed
        ad_session.started_at = now - timedelta(seconds=31)
        ad_session.eligible_at = now - timedelta(seconds=1)
        ad_session.save(update_fields=["started_at", "eligible_at"])

        valid_complete = self.client.post(
            reverse("advertisements:complete"),
            data=json.dumps(
                {
                    "ad_session_id": str(ad_session.id),
                    "nonce_token": ad_session.nonce_token,
                }
            ),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(valid_complete.status_code, 200)
        self.assertTrue(valid_complete.json()["free_access_granted"])
