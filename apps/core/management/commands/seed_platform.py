"""Management command to initialize default SiteConfiguration and Instagram Utility Tools."""
from django.core.management.base import BaseCommand

from apps.core.models import SiteConfiguration
from apps.downloads.models import Tool
from apps.downloads.services import DEFAULT_TOOLS


class Command(BaseCommand):
    help = "Seed default SiteConfiguration and Instagram utility tools for InSave Hub."

    def handle(self, *args, **options) -> None:
        config = SiteConfiguration.get_solo()
        self.stdout.write(
            self.style.SUCCESS(f"SiteConfiguration active: {config.site_name} ({config.tagline})")
        )

        created_count = 0
        for item in DEFAULT_TOOLS:
            _, created = Tool.objects.update_or_create(
                slug=item["slug"],
                defaults=item,
            )
            if created:
                created_count += 1

        total_tools = Tool.objects.count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Synchronized {total_tools} Instagram utility tools ({created_count} newly created)."
            )
        )
