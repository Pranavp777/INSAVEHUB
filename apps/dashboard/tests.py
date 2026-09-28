"""Tests for User Dashboard authorization and Admin Analytics permission enforcement."""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class DashboardAndAdminPermissionTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.regular_user = User.objects.create_user(
            username="regular_op",
            email="regular@example.com",
            password="RegularPassword123!",
        )
        self.admin_user = User.objects.create_superuser(
            username="admin_op",
            email="admin@example.com",
            password="AdminPassword123!",
        )

    def test_unauthenticated_dashboard_requests_redirect_to_login(self) -> None:
        resp = self.client.get(reverse("dashboard:index"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("accounts:login"), resp["Location"])

    def test_admin_analytics_blocks_regular_user_with_403_and_allows_staff(self) -> None:
        # Regular user receives 403 Forbidden on Admin Analytics
        self.client.login(username="regular_op", password="RegularPassword123!")
        user_dash = self.client.get(reverse("dashboard:index"))
        self.assertEqual(user_dash.status_code, 200)

        forbidden_resp = self.client.get(reverse("dashboard:admin_analytics"))
        self.assertEqual(forbidden_resp.status_code, 403)

        # Staff/Admin user receives 200 OK and can update platform configuration
        self.client.login(username="admin_op", password="AdminPassword123!")
        admin_resp = self.client.get(reverse("dashboard:admin_analytics"))
        self.assertEqual(admin_resp.status_code, 200)
        self.assertContains(admin_resp, "Admin Analytics")
