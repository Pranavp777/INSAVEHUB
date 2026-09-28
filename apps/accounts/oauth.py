"""
Google OAuth 2.0 Authentication Service for InSave Hub.
Implements state verification, session expiration checks, token exchange,
userinfo validation, and safe duplicate-email account linking.
"""
import re
import secrets
import time
from typing import Any, Dict, Tuple
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import HttpRequest

from apps.accounts.models import Profile

User = get_user_model()

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v3/userinfo"
OAUTH_STATE_MAX_AGE_SECONDS = 600  # 10 minutes


class GoogleOAuthError(Exception):
    """Structured exception for Google OAuth 2.0 flow errors."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def build_google_authorization_url(request: HttpRequest) -> str:
    """
    Generate the Google OAuth 2.0 authorization URL and persist a cryptographic
    CSRF state token and timestamp in the server-side session.
    """
    client_id = getattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "").strip()
    redirect_uri = getattr(settings, "GOOGLE_OAUTH_REDIRECT_URI", "").strip()
    if not client_id or not redirect_uri:
        raise GoogleOAuthError(
            "oauth_not_configured",
            "Google OAuth 2.0 credentials are not configured in the environment.",
        )

    state_token = secrets.token_urlsafe(32)
    request.session["google_oauth_state"] = state_token
    request.session["google_oauth_state_ts"] = int(time.time())
    request.session.modified = True

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state_token,
        "access_type": "online",
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTH_ENDPOINT}?{urlencode(params)}"


def validate_oauth_callback_state(request: HttpRequest) -> str:
    """
    Validate incoming callback query parameters, checking for cancelled auth,
    provider errors, missing state, session expiration, and state mismatch.
    Returns the authorization code on success.
    """
    provider_error = request.GET.get("error", "").strip()
    if provider_error:
        if provider_error == "access_denied":
            raise GoogleOAuthError(
                "cancelled",
                "Google authentication was cancelled before completion.",
            )
        raise GoogleOAuthError(
            "provider_error",
            f"Google returned an authentication error: {provider_error}.",
        )

    incoming_state = request.GET.get("state", "").strip()
    incoming_code = request.GET.get("code", "").strip()

    if not incoming_state or not incoming_code:
        raise GoogleOAuthError(
            "invalid_callback",
            "Invalid OAuth callback parameters. Missing authorization code or state.",
        )

    stored_state = request.session.pop("google_oauth_state", None)
    stored_ts = request.session.pop("google_oauth_state_ts", None)

    if not stored_state or stored_ts is None:
        raise GoogleOAuthError(
            "session_expired",
            "Your authentication session expired. Please initiate Google Sign-In again.",
        )

    elapsed = int(time.time()) - int(stored_ts)
    if elapsed > OAUTH_STATE_MAX_AGE_SECONDS or elapsed < -5:
        raise GoogleOAuthError(
            "session_expired",
            "The OAuth authorization window timed out. Please sign in again.",
        )

    if not secrets.compare_digest(str(stored_state), str(incoming_state)):
        raise GoogleOAuthError(
            "invalid_callback",
            "OAuth security state verification failed. Request rejected.",
        )

    return incoming_code


def exchange_code_for_userinfo(code: str) -> Dict[str, Any]:
    """Exchange authorization code for access token and fetch verified Google profile."""
    client_id = getattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "").strip()
    client_secret = getattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
    redirect_uri = getattr(settings, "GOOGLE_OAUTH_REDIRECT_URI", "").strip()

    if not client_id or not client_secret:
        raise GoogleOAuthError(
            "oauth_not_configured",
            "Google OAuth client credentials are not configured.",
        )

    try:
        token_resp = requests.post(
            GOOGLE_TOKEN_ENDPOINT,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
    except requests.RequestException as exc:
        raise GoogleOAuthError(
            "network_error",
            "Unable to reach Google OAuth token endpoint.",
        ) from exc

    if token_resp.status_code != 200:
        raise GoogleOAuthError(
            "token_exchange_failed",
            "Google rejected the authorization code exchange.",
        )

    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise GoogleOAuthError(
            "token_exchange_failed",
            "Google token response did not include an access token.",
        )

    try:
        userinfo_resp = requests.get(
            GOOGLE_USERINFO_ENDPOINT,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
    except requests.RequestException as exc:
        raise GoogleOAuthError(
            "network_error",
            "Unable to retrieve profile information from Google.",
        ) from exc

    if userinfo_resp.status_code != 200:
        raise GoogleOAuthError(
            "userinfo_failed",
            "Failed to verify Google user profile data.",
        )

    userinfo = userinfo_resp.json()
    sub = str(userinfo.get("sub", "")).strip()
    email = str(userinfo.get("email", "")).strip().lower()
    email_verified = bool(userinfo.get("email_verified", False))

    if not sub or not email:
        raise GoogleOAuthError(
            "invalid_userinfo",
            "Google account response is missing required identifier or email fields.",
        )
    if not email_verified:
        raise GoogleOAuthError(
            "unverified_google_email",
            "Your Google email address must be verified before signing in.",
        )

    return {
        "sub": sub,
        "email": email,
        "name": str(userinfo.get("name", "")).strip(),
        "picture": str(userinfo.get("picture", "")).strip(),
        "email_verified": email_verified,
    }


def _generate_unique_username(email: str, name: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9_.-]", "", name.lower().replace(" ", "_"))
    if len(base) < 3:
        base = re.sub(r"[^a-zA-Z0-9_.-]", "", email.split("@")[0].lower())
    base = (base or "insave_user")[:28]

    candidate = base
    counter = 1
    while User.objects.filter(username__iexact=candidate).exists():
        suffix = f"_{counter}"
        candidate = f"{base[:36 - len(suffix)]}{suffix}"
        counter += 1
    return candidate


@transaction.atomic
def resolve_or_create_google_user(userinfo: Dict[str, Any]) -> Tuple[Any, bool]:
    """
    Retrieve an existing user or create a new user from verified Google OAuth data.
    Handles:
    1. Existing Profile matched by `google_sub_id`
    2. Existing User matched by `email` (safe duplicate-email linking without creating duplicates)
    3. New User creation with unusable password (never storing Google passwords)
    Returns (user, created_boolean).
    """
    sub = userinfo["sub"]
    email = userinfo["email"]
    name = userinfo.get("name") or email.split("@")[0]
    picture = userinfo.get("picture") or ""

    # 1. Check existing profile by Google sub ID
    existing_profile = Profile.objects.select_related("user").filter(google_sub_id=sub).first()
    if existing_profile is not None:
        user = existing_profile.user
        if not user.is_active:
            raise GoogleOAuthError("account_disabled", "This user account has been disabled.")
        update_fields = ["updated_at"]
        if not existing_profile.email_verified:
            existing_profile.email_verified = True
            update_fields.append("email_verified")
        if picture and not existing_profile.avatar_url:
            existing_profile.avatar_url = picture
            update_fields.append("avatar_url")
        existing_profile.save(update_fields=update_fields)
        return user, False

    # 2. Check existing user by email (handle duplicate email safely)
    existing_user = User.objects.filter(email__iexact=email).first()
    if existing_user is not None:
        if not existing_user.is_active:
            raise GoogleOAuthError("account_disabled", "This user account has been disabled.")
        profile, _ = Profile.objects.get_or_create(user=existing_user)
        if profile.google_sub_id and profile.google_sub_id != sub:
            raise GoogleOAuthError(
                "duplicate_email_conflict",
                "This email address is already linked to a different Google identity.",
            )
        profile.google_sub_id = sub
        profile.email_verified = True
        if not profile.display_name:
            profile.display_name = name
        if picture and not profile.avatar_url:
            profile.avatar_url = picture
        profile.save()
        return existing_user, False

    # 3. Create new user without password
    username = _generate_unique_username(email=email, name=name)
    new_user = User(
        username=username,
        email=email,
        first_name=name.split(" ")[0][:30] if name else "",
        last_name=" ".join(name.split(" ")[1:])[:150] if " " in name else "",
    )
    new_user.set_unusable_password()
    new_user.save()

    profile, _ = Profile.objects.get_or_create(user=new_user)
    profile.display_name = name[:120]
    profile.avatar_url = picture[:500]
    profile.auth_provider = Profile.AuthProvider.GOOGLE
    profile.google_sub_id = sub
    profile.email_verified = True
    profile.save()

    return new_user, True
