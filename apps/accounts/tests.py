"""Tests for Registration, Login, Google OAuth 2.0 flow, Password Reset, and Email Verification."""
import time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.accounts.models import Profile

User = get_user_model()


class AuthenticationAndOAuthTests(TestCase):
    def setUp(self) -> None:
        cache.clear()

    def test_registration_and_email_verification_flow(self) -> None:
        response = self.client.post(
            reverse("accounts:register"),
            {
                "username": "orbital_user",
                "display_name": "Orbital Operator",
                "email": "operator@example.com",
                "password": "ComplexPassword987!",
                "password_confirm": "ComplexPassword987!",
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="orbital_user")
        profile = Profile.objects.get(user=user)
        self.assertFalse(profile.email_verified)
        self.assertTrue(bool(profile.email_verification_token))

        # Verify email using token
        verify_resp = self.client.get(
            reverse("accounts:verify_email", kwargs={"token": profile.email_verification_token})
        )
        self.assertEqual(verify_resp.status_code, 200)
        profile.refresh_from_db()
        self.assertTrue(profile.email_verified)

    def test_login_with_username_and_email(self) -> None:
        user = User.objects.create_user(
            username="pilot01",
            email="pilot01@example.com",
            password="SecurePass123!",
        )
        # Login via username
        resp1 = self.client.post(
            reverse("accounts:login"),
            {"identifier": "pilot01", "password": "SecurePass123!"},
        )
        self.assertRedirects(resp1, reverse("dashboard:index"))
        self.client.get(reverse("accounts:logout"))

        # Login via email
        resp2 = self.client.post(
            reverse("accounts:login"),
            {"identifier": "pilot01@example.com", "password": "SecurePass123!"},
        )
        self.assertRedirects(resp2, reverse("dashboard:index"))

    def test_password_reset_flow(self) -> None:
        user = User.objects.create_user(
            username="reset_user",
            email="reset@example.com",
            password="OldPassword123!",
        )
        forgot_resp = self.client.post(
            reverse("accounts:forgot_password"),
            {"email": "reset@example.com"},
        )
        self.assertEqual(forgot_resp.status_code, 200)
        self.assertContains(forgot_resp, "cryptographic password reset link")

        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        confirm_url = reverse(
            "accounts:password_reset_confirm",
            kwargs={"uidb64": uidb64, "token": token},
        )

        reset_resp = self.client.post(
            confirm_url,
            {
                "new_password": "UpdatedPassword456!",
                "confirm_password": "UpdatedPassword456!",
            },
        )
        self.assertRedirects(reset_resp, reverse("accounts:login"))
        user.refresh_from_db()
        self.assertTrue(user.check_password("UpdatedPassword456!"))

    @override_settings(
        GOOGLE_OAUTH_CLIENT_ID="test-google-client-id",
        GOOGLE_OAUTH_CLIENT_SECRET="test-google-secret",
        GOOGLE_OAUTH_REDIRECT_URI="http://testserver/auth/google/callback/",
    )
    @patch("apps.accounts.oauth.exchange_code_for_userinfo")
    def test_google_oauth_flow_new_and_duplicate_email_and_errors(self, mock_exchange) -> None:
        # 1. Initiate OAuth redirect
        init_resp = self.client.get(reverse("accounts:google_login"))
        self.assertEqual(init_resp.status_code, 302)
        self.assertIn("accounts.google.com/o/oauth2/v2/auth", init_resp["Location"])
        state = self.client.session["google_oauth_state"]

        # 2. Callback creates new Google user without storing password
        mock_exchange.return_value = {
            "sub": "google-sub-1001",
            "email": "oauth_user@example.com",
            "name": "Google User",
            "picture": "https://example.com/photo.jpg",
            "email_verified": True,
        }
        cb_resp = self.client.get(
            reverse("accounts:google_callback"),
            {"code": "valid-auth-code", "state": state},
        )
        self.assertRedirects(cb_resp, reverse("dashboard:index"))
        created_user = User.objects.get(email="oauth_user@example.com")
        self.assertFalse(created_user.has_usable_password())
        self.assertEqual(created_user.profile.google_sub_id, "google-sub-1001")

        self.client.get(reverse("accounts:logout"))

        # 3. Duplicate email handling: existing email user logs in via Google safely
        existing_user = User.objects.create_user(
            username="existing_member",
            email="existing@example.com",
            password="StandardPassword123!",
        )
        self.client.get(reverse("accounts:google_login"))
        state2 = self.client.session["google_oauth_state"]
        mock_exchange.return_value = {
            "sub": "google-sub-2002",
            "email": "existing@example.com",
            "name": "Existing Member",
            "picture": "",
            "email_verified": True,
        }
        cb_resp2 = self.client.get(
            reverse("accounts:google_callback"),
            {"code": "code-2", "state": state2},
        )
        self.assertRedirects(cb_resp2, reverse("dashboard:index"))
        existing_user.profile.refresh_from_db()
        self.assertEqual(existing_user.profile.google_sub_id, "google-sub-2002")

        self.client.get(reverse("accounts:logout"))

        # 4. Cancelled OAuth error handling
        cancel_resp = self.client.get(
            reverse("accounts:google_callback"),
            {"error": "access_denied"},
        )
        self.assertRedirects(cancel_resp, reverse("accounts:login"))

        # 5. Session expiration handling
        session = self.client.session
        session["google_oauth_state"] = "expired-state"
        session["google_oauth_state_ts"] = int(time.time()) - 1200
        session.save()
        exp_resp = self.client.get(
            reverse("accounts:google_callback"),
            {"code": "code-3", "state": "expired-state"},
        )
        self.assertRedirects(exp_resp, reverse("accounts:login"))
