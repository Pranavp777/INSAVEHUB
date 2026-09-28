"""Signals to guarantee Profile creation for every User."""
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.accounts.models import Profile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_profile_exists(sender, instance, created: bool, **kwargs) -> None:
    if created:
        Profile.objects.get_or_create(
            user=instance,
            defaults={
                "display_name": instance.get_full_name() or instance.username,
            },
        )
