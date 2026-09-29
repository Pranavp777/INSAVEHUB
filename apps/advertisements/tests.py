"""
Tests for the 30-second server-validated AdSession, refresh-bypass protection,
24-hour FreeAccessSession unlock, and access expiration lifecycle.
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

    def test_full_download_to_30s_ad_to_24h_free_access_and_expiration_cycle(self) -> None:
        # 1. First download is allowed immediately without an advertisement
        r1 = self.client.post(
            reverse("downloads:analyze_api"),
            data=json.dumps({"url": "https://www.instagram.com/reel/FirstReel01/"}),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(r1.status_code, 200)
        dl1_exec_url = r1.json()["download"]["execute_url"]

        exec1 = self.client.get(dl1_exec_url)
        self.assertEqual(exec1.status_code, 200)
        self.assertIn("attachment", exec1["Content-Disposition"])

        # 2. Second download requires the 30-second advertisement
        r2 = self.client.post(
            reverse("downloads:analyze_api"),
            data=json.dumps({"url": "https://www.instagram.com/reel/SecondReel02/"}),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        self.assertTrue(r2.json()["access"]["ad_required"])
        dl2_exec_url = r2.json()["download"]["execute_url"]

        # Attempting to execute download 2 before completing ad redirects to ad gate (or 403 JSON)
        exec2_blocked = self.client.get(dl2_exec_url, HTTP_ACCEPT="application/json")
        self.assertEqual(exec2_blocked.status_code, 403)
        self.assertEqual(exec2_blocked.json()["code"], "advertisement_required")

        # 3. Visit Ad Gate screen and verify required message & session persistence on refresh
        gate_resp1 = self.client.get(reverse("advertisements:gate"))
        self.assertEqual(gate_resp1.status_code, 200)
        self.assertContains(
            gate_resp1,
            "Your next download will be available after the advertisement.",
        )
        ad_session = AdSession.objects.first()
        self.assertIsNotNone(ad_session)

        # Refreshing the ad gate reuses the exact same AdSession (does not bypass countdown)
        gate_resp2 = self.client.get(reverse("advertisements:gate"))
        self.assertEqual(gate_resp2.status_code, 200)
        self.assertEqual(AdSession.objects.count(), 1)

        # 4. Premature completion attempt (before 30 server seconds have elapsed) is rejected with 403
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

        # 5. Simulate 30 seconds elapsed on the server clock
        ad_session.started_at = timezone.now() - timedelta(seconds=31)
        ad_session.eligible_at = timezone.now() - timedelta(seconds=1)
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

        # 6. Verify 24-hour FreeAccessSession is now active and allows multiple downloads without ad
        free_session = FreeAccessSession.objects.filter(is_active=True).first()
        self.assertIsNotNone(free_session)
        self.assertGreater(free_session.remaining_seconds, 23 * 3600)

        exec2_unlocked = self.client.get(dl2_exec_url)
        self.assertEqual(exec2_unlocked.status_code, 200)

        # Third download during 24h window also succeeds without interstitial
        r3 = self.client.post(
            reverse("downloads:analyze_api"),
            data=json.dumps({"url": "https://www.instagram.com/reel/ThirdReel03/"}),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        self.assertFalse(r3.json()["access"]["ad_required"])
        exec3 = self.client.get(r3.json()["download"]["execute_url"])
        self.assertEqual(exec3.status_code, 200)

        # 7. Expire the 24-hour period on the server clock -> returns to normal access flow
        free_session.expires_at = timezone.now() - timedelta(minutes=1)
        free_session.save(update_fields=["expires_at"])

        # Post-expiration: first download in the new cycle is allowed, then ad is required again
        r4 = self.client.post(
            reverse("downloads:analyze_api"),
            data=json.dumps({"url": "https://www.instagram.com/reel/PostExpire01/"}),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        self.assertFalse(r4.json()["access"]["ad_required"])
        self.client.get(r4.json()["download"]["execute_url"])

        r5 = self.client.post(
            reverse("downloads:analyze_api"),
            data=json.dumps({"url": "https://www.instagram.com/reel/PostExpire02/"}),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        self.assertTrue(r5.json()["access"]["ad_required"])

    def test_5s_initial_ad_and_download_session_4_states(self) -> None:
        from apps.advertisements.models import DownloadSession

        # State 1: First download analyze -> initial_5s_ad_required is True
        r1 = self.client.post(
            reverse("downloads:analyze_api"),
            data=json.dumps({"url": "https://www.instagram.com/reel/StateOneReel/"}),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(r1.status_code, 200)
        access1 = r1.json()["access"]
        self.assertEqual(access1["state"], "STATE_1_FIRST_DOWNLOAD")
        self.assertTrue(access1["initial_5s_ad_required"])
        dl_id = r1.json()["download"]["id"]
        dl_exec_url = r1.json()["download"]["execute_url"]

        # Visit 5-second advertisement page (?mode=5s)
        gate_5s = self.client.get(f"{reverse('advertisements:gate')}?download_id={dl_id}&mode=5s")
        self.assertEqual(gate_5s.status_code, 200)
        self.assertContains(gate_5s, "ADVERTISEMENT")
        self.assertContains(gate_5s, "Your download will begin shortly.")
        self.assertContains(gate_5s, "00:05")

        ad_5s = AdSession.objects.filter(ad_type=AdSession.AdType.INITIAL_5S).first()
        self.assertIsNotNone(ad_5s)
        self.assertEqual(ad_5s.required_duration_seconds, 5)

        # Simulate 5 seconds elapsed -> complete 5s ad (does NOT grant 24h access yet)
        ad_5s.started_at = timezone.now() - timedelta(seconds=6)
        ad_5s.eligible_at = timezone.now() - timedelta(seconds=1)
        ad_5s.save(update_fields=["started_at", "eligible_at"])

        complete_5s = self.client.post(
            reverse("advertisements:complete"),
            data=json.dumps(
                {
                    "ad_session_id": str(ad_5s.id),
                    "nonce_token": ad_5s.nonce_token,
                }
            ),
            content_type="application/json",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(complete_5s.status_code, 200)
        self.assertFalse(complete_5s.json()["free_access_granted"])
        self.assertIn("auto_download=1", complete_5s.json()["redirect_url"])

        # Execute the first download after the 5-second ad completes
        exec_resp = self.client.get(dl_exec_url)
        self.assertEqual(exec_resp.status_code, 200)

        # Verify DownloadSession has first_download_completed=True, ad_completed=False
        ds = DownloadSession.objects.first()
        self.assertIsNotNone(ds)
        self.assertTrue(ds.first_download_completed)
        self.assertFalse(ds.ad_completed)

        # Verify /ads/access-status/ now returns STATE_2_AD_REQUIRED
        status_resp = self.client.get(reverse("advertisements:access_status"))
        self.assertEqual(status_resp.status_code, 200)
        self.assertEqual(status_resp.json()["access"]["state"], "STATE_2_AD_REQUIRED")
        self.assertTrue(status_resp.json()["access"]["ad_required"])

        # Verify Home page contains the "Unlock 24 Hours Free" popup modal
        home_resp = self.client.get(reverse("core:home"))
        self.assertContains(home_resp, "Unlock 24 Hours Free")
        self.assertContains(
            home_resp,
            "Watch a 30-second advertisement and enjoy ad-free downloads for the next 24 hours.",
        )
        self.assertContains(home_resp, "Watch Ad")
        self.assertContains(home_resp, "Not now")

