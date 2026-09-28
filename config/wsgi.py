"""
WSGI config for InSave Hub.
Exposes the WSGI callable as a module-level variable named ``application``.
Compatible with Cloudflare Python Workers WSGI integration and traditional WSGI servers.
"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()
