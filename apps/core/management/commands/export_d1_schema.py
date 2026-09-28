"""Management command to export SQLite / Cloudflare D1 compatible SQL schema."""
import sqlite3
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Export current database schema and seed rows into a Cloudflare D1 compatible SQL file."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--output",
            type=str,
            default="d1_schema.sql",
            help="Target SQL file path (default: d1_schema.sql)",
        )

    def handle(self, *args, **options) -> None:
        db_name = settings.DATABASES["default"]["NAME"]
        out_path = Path(settings.BASE_DIR) / options["output"]

        conn = sqlite3.connect(str(db_name))
        lines = [
            "-- InSave Hub Cloudflare D1 Compatible SQL Export",
            "PRAGMA foreign_keys=OFF;",
        ]
        for line in conn.iterdump():
            if line in ("BEGIN TRANSACTION;", "COMMIT;"):
                continue
            if "sqlite_sequence" in line:
                continue
            lines.append(line)
        conn.close()

        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.stdout.write(
            self.style.SUCCESS(f"Exported Cloudflare D1 SQL schema to {out_path}")
        )
