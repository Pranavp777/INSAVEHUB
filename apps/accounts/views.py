"""Authentication, Google OAuth 2.0, Password Reset, Email Verification, and Profile views."""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from apps.accounts import oauth
from apps.accounts.forms import (
    ForgotPasswordForm,
    LoginForm,
    ProfileUpdateForm,
    RegistrationForm,
    SetNewPasswordForm,
)
from apps.accounts.models import Profile, get_or_create_user_profile
from apps.accounts.oauth import GoogleOAuthError
from apps.core.models import AuditLog, SiteConfiguration
from apps.core.rate_limit import rate_limit
from apps.core.utils import get_ip_hash

User = get_user_model()


def _send_verification_email(request: HttpRequest, user, token: str) -> None:
    verify_path = reverse("accounts:verify_email", kwargs={"token": token})
    base_url = getattr(settings, "CANONICAL_BASE_URL", "http://localhost:8000").rstrip("/")
    verify_url = f"{base_url}{verify_path}"
    subject = "Verify your InSave Hub account"
    body = (
        f"Hello {user.username},\n\n"
        f"Please confirm your email address for InSave Hub by visiting the link below:\n\n"
        f"{verify_url}\n\n"
        f"If you did not create this account, you may safely disregard this message."
    )
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )
    except Exception:
        pass


@rate_limit("auth", methods=("POST",))
def login_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("dashboard:index")

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid() and form.authenticated_user is not None:
            user = form.authenticated_user
            login(request, user)
            profile = get_or_create_user_profile(user)
            if profile:
                profile.last_login_ip_hash = get_ip_hash(request)
                profile.save(update_fields=["last_login_ip_hash", "updated_at"])

            AuditLog.record(
                event_type="auth.login_success",
                description=f"User '{user.username}' authenticated via credentials.",
                request=request,
                user=user,
            )
            messages.success(request, "Authentication verified. Welcome back to the control center.")
            next_url = request.GET.get("next") or request.POST.get("next") or ""
            if next_url and next_url.startswith("/") and not next_url.startswith("//"):
                return redirect(next_url)
            return redirect("dashboard:index")
        else:
            AuditLog.record(
                event_type="auth.login_failed",
                description="Failed credential login attempt.",
                request=request,
                severity=AuditLog.Severity.WARNING,
            )
    else:
        form = LoginForm(request)

    return render(
        request,
        "auth/login.html",
        {
            "page_title": "Sign In | InSave Hub",
            "meta_description": "Sign in to your InSave Hub control center.",
            "form": form,
        },
    )


@rate_limit("auth", methods=("POST",))
def register_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("dashboard:index")

    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data["username"]
            email = form.cleaned_data["email"]
            display_name = form.cleaned_data.get("display_name") or username
            password = form.cleaned_data["password"]

            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
            )
            profile = get_or_create_user_profile(user)
            token = ""
            if profile:
                profile.display_name = display_name[:120]
                profile.auth_provider = Profile.AuthProvider.EMAIL
                profile.last_login_ip_hash = get_ip_hash(request)
                profile.save()
                token = profile.issue_verification_token()

            _send_verification_email(request, user, token)
            login(request, user)

            AuditLog.record(
                event_type="auth.register_success",
                description=f"New account registered for '{user.username}'.",
                request=request,
                user=user,
            )
            messages.success(
                request,
                "Account initialized. A verification link has been dispatched to your email address.",
            )
            return redirect("accounts:account_confirmation")
    else:
        form = RegistrationForm()

    return render(
        request,
        "auth/register.html",
        {
            "page_title": "Create Account | InSave Hub",
            "meta_description": "Create an InSave Hub account to track download history and 24-hour passes.",
            "form": form,
        },
    )


def logout_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        AuditLog.record(
            event_type="auth.logout",
            description=f"User '{request.user.username}' signed out.",
            request=request,
            user=request.user,
        )
        logout(request)
        messages.info(request, "Your session has been terminated securely.")
    return redirect("core:home")


@rate_limit("oauth", methods=("GET", "POST"))
def google_login_initiate(request: HttpRequest) -> HttpResponse:
    config = SiteConfiguration.get_solo()
    if not config.enable_google_oauth:
        messages.error(request, "Google OAuth authentication is currently disabled by the administrator.")
        return redirect("accounts:login")

    try:
        auth_url = oauth.build_google_authorization_url(request)
        return redirect(auth_url)
    except GoogleOAuthError as exc:
        AuditLog.record(
            event_type="auth.google_initiate_error",
            description=exc.message,
            request=request,
            severity=AuditLog.Severity.WARNING,
            metadata={"code": exc.code},
        )
        messages.error(request, exc.message)
        return redirect("accounts:login")


@rate_limit("oauth", methods=("GET",))
def google_login_callback(request: HttpRequest) -> HttpResponse:
    try:
        code = oauth.validate_oauth_callback_state(request)
        userinfo = oauth.exchange_code_for_userinfo(code)
        user, created = oauth.resolve_or_create_google_user(userinfo)

        login(request, user)
        profile = get_or_create_user_profile(user)
        if profile:
            profile.last_login_ip_hash = get_ip_hash(request)
            profile.save(update_fields=["last_login_ip_hash", "updated_at"])

        AuditLog.record(
            event_type="auth.google_success",
            description=f"Google OAuth 2.0 login succeeded for '{user.email}' (created={created}).",
            request=request,
            user=user,
        )
        messages.success(request, "Authenticated via Google OAuth 2.0.")
        return redirect("dashboard:index")

    except GoogleOAuthError as exc:
        AuditLog.record(
            event_type="auth.google_callback_error",
            description=exc.message,
            request=request,
            severity=AuditLog.Severity.WARNING,
            metadata={"code": exc.code},
        )
        messages.error(request, exc.message)
        return redirect("accounts:login")


@rate_limit("password_reset", methods=("POST",))
def forgot_password_view(request: HttpRequest) -> HttpResponse:
    reset_dispatched = False
    if request.method == "POST":
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].strip().lower()
            user = User.objects.filter(email__iexact=email, is_active=True).first()
            if user is not None:
                uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)
                reset_path = reverse(
                    "accounts:password_reset_confirm",
                    kwargs={"uidb64": uidb64, "token": token},
                )
                base_url = getattr(settings, "CANONICAL_BASE_URL", "http://localhost:8000").rstrip("/")
                reset_url = f"{base_url}{reset_path}"
                try:
                    send_mail(
                        subject="InSave Hub Password Reset Request",
                        message=(
                            f"Hello {user.username},\n\n"
                            f"A password reset was requested for your InSave Hub account.\n"
                            f"Use the secure link below to set a new password:\n\n"
                            f"{reset_url}\n\n"
                            f"If you did not initiate this request, no changes have been made."
                        ),
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[user.email],
                        fail_silently=True,
                    )
                except Exception:
                    pass

            AuditLog.record(
                event_type="auth.password_reset_requested",
                description="Password recovery link requested.",
                request=request,
            )
            reset_dispatched = True
    else:
        form = ForgotPasswordForm()

    return render(
        request,
        "auth/forgot_password.html",
        {
            "page_title": "Reset Password | InSave Hub",
            "meta_description": "Recover access to your InSave Hub account.",
            "form": form,
            "reset_dispatched": reset_dispatched,
        },
    )


def password_reset_confirm_view(request: HttpRequest, uidb64: str, token: str) -> HttpResponse:
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid, is_active=True)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    valid_link = user is not None and default_token_generator.check_token(user, token)

    if request.method == "POST" and valid_link and user is not None:
        form = SetNewPasswordForm(user=user, data=request.POST)
        if form.is_valid():
            user.set_password(form.cleaned_data["new_password"])
            user.save()
            AuditLog.record(
                event_type="auth.password_reset_completed",
                description=f"Password reset completed for user '{user.username}'.",
                request=request,
                user=user,
            )
            messages.success(request, "Your password has been updated. You may now sign in.")
            return redirect("accounts:login")
    else:
        form = SetNewPasswordForm(user=user)

    return render(
        request,
        "auth/password_reset_confirm.html",
        {
            "page_title": "Set New Password | InSave Hub",
            "form": form,
            "valid_link": valid_link,
        },
    )


def verify_email_view(request: HttpRequest, token: str) -> HttpResponse:
    clean_token = (token or "").strip()
    profile = (
        Profile.objects.select_related("user")
        .filter(email_verification_token=clean_token)
        .exclude(email_verification_token="")
        .first()
    )
    verified = False
    if profile is not None:
        profile.mark_email_verified()
        verified = True
        AuditLog.record(
            event_type="auth.email_verified",
            description=f"Email verified for user '{profile.user.username}'.",
            request=request,
            user=profile.user,
        )
        messages.success(request, "Your email address has been verified.")

    return render(
        request,
        "auth/verify_email.html",
        {
            "page_title": "Email Verification | InSave Hub",
            "verified": verified,
        },
    )


@login_required
def account_confirmation_view(request: HttpRequest) -> HttpResponse:
    profile = get_or_create_user_profile(request.user)
    return render(
        request,
        "auth/account_confirmation.html",
        {
            "page_title": "Account Confirmation | InSave Hub",
            "profile": profile,
        },
    )


@login_required
@rate_limit("auth", methods=("POST",))
def resend_verification_view(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        profile = get_or_create_user_profile(request.user)
        if profile and not profile.email_verified:
            token = profile.issue_verification_token()
            _send_verification_email(request, request.user, token)
            messages.success(request, "A new verification link has been sent to your email address.")
        else:
            messages.info(request, "Your email address is already verified.")
    return redirect("accounts:account_confirmation")


@login_required
def profile_view(request: HttpRequest) -> HttpResponse:
    profile = get_or_create_user_profile(request.user)
    password_form = SetNewPasswordForm(user=request.user)

    if request.method == "POST":
        action = request.POST.get("form_action", "update_profile")
        if action == "change_password":
            password_form = SetNewPasswordForm(user=request.user, data=request.POST)
            profile_form = ProfileUpdateForm(
                user=request.user,
                initial={
                    "display_name": profile.display_name if profile else request.user.username,
                    "email": request.user.email,
                    "avatar_url": profile.avatar_url if profile else "",
                    "security_alerts_enabled": profile.security_alerts_enabled if profile else True,
                },
            )
            if password_form.is_valid():
                request.user.set_password(password_form.cleaned_data["new_password"])
                request.user.save()
                update_session_auth_hash(request, request.user)
                AuditLog.record(
                    event_type="account.password_changed",
                    description="User updated account password from profile panel.",
                    request=request,
                    user=request.user,
                )
                messages.success(request, "Account password updated.")
                return redirect("accounts:profile")
        else:
            profile_form = ProfileUpdateForm(user=request.user, data=request.POST)
            if profile_form.is_valid():
                new_email = profile_form.cleaned_data["email"]
                email_changed = new_email.lower() != (request.user.email or "").lower()
                request.user.email = new_email
                request.user.save(update_fields=["email"])

                if profile:
                    profile.display_name = profile_form.cleaned_data["display_name"]
                    profile.avatar_url = profile_form.cleaned_data.get("avatar_url") or ""
                    profile.security_alerts_enabled = bool(
                        profile_form.cleaned_data.get("security_alerts_enabled")
                    )
                    if email_changed:
                        profile.email_verified = False
                        token = profile.issue_verification_token()
                        _send_verification_email(request, request.user, token)
                    profile.save()

                AuditLog.record(
                    event_type="account.profile_updated",
                    description="User updated profile metadata.",
                    request=request,
                    user=request.user,
                )
                messages.success(request, "Profile settings saved.")
                return redirect("accounts:profile")
    else:
        profile_form = ProfileUpdateForm(
            user=request.user,
            initial={
                "display_name": profile.display_name if profile else request.user.username,
                "email": request.user.email,
                "avatar_url": profile.avatar_url if profile else "",
                "security_alerts_enabled": profile.security_alerts_enabled if profile else True,
            },
        )

    from apps.donations.models import Donation
    from apps.downloads.models import Download

    user_downloads = Download.objects.filter(user=request.user)
    total_downloads = user_downloads.count()
    completed_downloads = user_downloads.filter(status=Download.Status.COMPLETED).count()
    user_donations = Donation.objects.filter(user=request.user).order_by("-created_at")[:10]
    recent_security_logs = AuditLog.objects.filter(user=request.user).order_by("-created_at")[:6]

    return render(
        request,
        "accounts/profile.html",
        {
            "page_title": "User Profile & Security | InSave Hub",
            "profile": profile,
            "profile_form": profile_form,
            "password_form": password_form,
            "total_downloads": total_downloads,
            "completed_downloads": completed_downloads,
            "user_donations": user_donations,
            "recent_security_logs": recent_security_logs,
        },
    )
