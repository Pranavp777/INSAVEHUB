from django.urls import path

from apps.accounts import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("register/", views.register_view, name="register"),
    path("logout/", views.logout_view, name="logout"),
    path("google/login/", views.google_login_initiate, name="google_login"),
    path("google/callback/", views.google_login_callback, name="google_callback"),
    path("forgot-password/", views.forgot_password_view, name="forgot_password"),
    path(
        "reset-password/<str:uidb64>/<str:token>/",
        views.password_reset_confirm_view,
        name="password_reset_confirm",
    ),
    path("verify-email/<str:token>/", views.verify_email_view, name="verify_email"),
    path("account-confirmation/", views.account_confirmation_view, name="account_confirmation"),
    path("resend-verification/", views.resend_verification_view, name="resend_verification"),
    path("profile/", views.profile_view, name="profile"),
]
