"""Profil explicite de développement : jamais importé par la production."""

import os
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

from config.codespaces_environment import origins

try:
    application_origin, _mailpit_origin = origins(os.environ)
except ValueError as error:
    raise ImproperlyConfigured(str(error)) from error

from config.settings import *  # noqa: E402,F403

APP_BASE_URL = application_origin
ALLOWED_HOSTS = [str(urlsplit(APP_BASE_URL).hostname), "localhost", "127.0.0.1", "[::1]"]
CSRF_TRUSTED_ORIGINS = [APP_BASE_URL]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_DOMAIN = None
CSRF_COOKIE_DOMAIN = None
# GitHub termine HTTPS ; HTTP est utilisé seulement dans le conteneur/Compose.
# On ne fait pas confiance à un en-tête X-Forwarded-Proto fourni par le client.
SECURE_PROXY_SSL_HEADER = None
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
EMAIL_HOST = "mailpit"
EMAIL_PORT = 1025
