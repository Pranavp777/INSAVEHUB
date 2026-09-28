"""Authentication and Profile management forms for InSave Hub."""
import re
from typing import Any

from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password

User = get_user_model()

USERNAME_REGEX = re.compile(r"^[a-zA-Z0-9_.-]{3,36}$")


class RegistrationForm(forms.Form):
    username = forms.CharField(
        max_length=36,
        min_length=3,
        label="Username",
        widget=forms.TextInput(
            attrs={
                "class": "glass-input",
                "placeholder": "username",
                "autocomplete": "username",
            }
        ),
    )
    display_name = forms.CharField(
        max_length=80,
        required=False,
        label="Full Name or Alias",
        widget=forms.TextInput(
            attrs={
                "class": "glass-input",
                "placeholder": "Alex Mercer",
                "autocomplete": "name",
            }
        ),
    )
    email = forms.EmailField(
        label="Email Address",
        widget=forms.EmailInput(
            attrs={
                "class": "glass-input",
                "placeholder": "name@domain.com",
                "autocomplete": "email",
            }
        ),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(
            attrs={
                "class": "glass-input",
                "placeholder": "Minimum 8 characters",
                "autocomplete": "new-password",
            }
        ),
    )
    password_confirm = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(
            attrs={
                "class": "glass-input",
                "placeholder": "Repeat password",
                "autocomplete": "new-password",
            }
        ),
    )

    def clean_username(self) -> str:
        username = self.cleaned_data["username"].strip()
        if not USERNAME_REGEX.match(username):
            raise forms.ValidationError(
                "Username must be 3-36 characters and contain only letters, numbers, dots, hyphens, or underscores."
            )
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("An account with this username already exists.")
        return username

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email address is already registered.")
        return email

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        password = cleaned.get("password")
        password_confirm = cleaned.get("password_confirm")
        if password and password_confirm:
            if password != password_confirm:
                self.add_error("password_confirm", "Passwords do not match.")
            else:
                validate_password(password)
        return cleaned


class LoginForm(forms.Form):
    identifier = forms.CharField(
        max_length=150,
        label="Username or Email",
        widget=forms.TextInput(
            attrs={
                "class": "glass-input",
                "placeholder": "username or email@domain.com",
                "autocomplete": "username",
            }
        ),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(
            attrs={
                "class": "glass-input",
                "placeholder": "Enter your password",
                "autocomplete": "current-password",
            }
        ),
    )

    def __init__(self, request=None, *args: Any, **kwargs: Any) -> None:
        self.request = request
        self.authenticated_user = None
        super().__init__(*args, **kwargs)

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        identifier = (cleaned.get("identifier") or "").strip()
        password = cleaned.get("password") or ""

        if identifier and password:
            username = identifier
            if "@" in identifier:
                matched = User.objects.filter(email__iexact=identifier).first()
                if matched:
                    username = matched.username

            user = authenticate(self.request, username=username, password=password)
            if user is None:
                raise forms.ValidationError(
                    "Invalid credentials. Please check your username or email and password."
                )
            if not user.is_active:
                raise forms.ValidationError("This account has been deactivated.")
            self.authenticated_user = user
        return cleaned


class ProfileUpdateForm(forms.Form):
    display_name = forms.CharField(
        max_length=120,
        required=True,
        label="Display Name",
        widget=forms.TextInput(attrs={"class": "glass-input"}),
    )
    email = forms.EmailField(
        required=True,
        label="Email Address",
        widget=forms.EmailInput(attrs={"class": "glass-input"}),
    )
    avatar_url = forms.URLField(
        required=False,
        label="Profile Photo URL (Optional)",
        widget=forms.URLInput(
            attrs={
                "class": "glass-input",
                "placeholder": "https://example.com/avatar.jpg",
            }
        ),
    )
    security_alerts_enabled = forms.BooleanField(
        required=False,
        label="Enable Security Audit Notifications",
    )

    def __init__(self, user, *args: Any, **kwargs: Any) -> None:
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_email(self) -> str:
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError("Another account is already using this email address.")
        return email


class ForgotPasswordForm(forms.Form):
    email = forms.EmailField(
        label="Registered Email Address",
        widget=forms.EmailInput(
            attrs={
                "class": "glass-input",
                "placeholder": "Enter your account email",
                "autocomplete": "email",
            }
        ),
    )


class SetNewPasswordForm(forms.Form):
    new_password = forms.CharField(
        label="New Password",
        widget=forms.PasswordInput(
            attrs={
                "class": "glass-input",
                "placeholder": "Minimum 8 characters",
                "autocomplete": "new-password",
            }
        ),
    )
    confirm_password = forms.CharField(
        label="Confirm New Password",
        widget=forms.PasswordInput(
            attrs={
                "class": "glass-input",
                "placeholder": "Repeat new password",
                "autocomplete": "new-password",
            }
        ),
    )

    def __init__(self, user=None, *args: Any, **kwargs: Any) -> None:
        self.user = user
        super().__init__(*args, **kwargs)

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        pw1 = cleaned.get("new_password")
        pw2 = cleaned.get("confirm_password")
        if pw1 and pw2:
            if pw1 != pw2:
                self.add_error("confirm_password", "Passwords do not match.")
            else:
                validate_password(pw1, user=self.user)
        return cleaned
