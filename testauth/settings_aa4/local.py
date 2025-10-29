# flake8: noqa

# Every setting in base.py can be overloaded by redefining it here.
from .base import *

# These are required for Django to function properly. Don't touch.
ROOT_URLCONF = "testauth.urls"
WSGI_APPLICATION = "testauth.wsgi.application"
SECRET_KEY = "t$@h+j#yqhmuy$x7$fkhytd&drajgfsb-6+j9pqn*vj0)gq&-2"

# This is where css/images will be placed for your webserver to read
STATIC_ROOT = "/var/www/testauth/static/"

# Change this to change the name of the auth site displayed
# in page titles and the site header.
SITE_NAME = "testauth"

# This is your websites URL, set it accordingly
# Make sure this URL is WITHOUT a trailing slash
SITE_URL = "http://127.0.0.1:8000"

# Django security
CSRF_TRUSTED_ORIGINS = [SITE_URL]

# Change this to enable/disable debug mode, which displays
# useful error messages but can leak sensitive data.
DEBUG = False

# Add any additional apps to this list.
INSTALLED_APPS += ["sri", "eveuniverse", "standingssync"]

# Enter credentials to use MySQL/MariaDB. Comment out to use sqlite3
"""
DATABASES['default'] = {
    'ENGINE': 'django.db.backends.mysql',
    'NAME': 'alliance_auth',
    'USER': '',
    'PASSWORD': '',
    'HOST': '127.0.0.1',
    'PORT': '3306',
    'OPTIONS': {'charset': 'utf8mb4'},
}
"""

# Register an application at https://developers.eveonline.com for Authentication
# & API Access and fill out these settings. Be sure to set the callback URL
# to https://example.com/sso/callback substituting your domain for example.com
# Logging in to auth requires the publicData scope (can be overridden through the
# LOGIN_TOKEN_SCOPES setting). Other apps may require more (see their docs).
ESI_SSO_CLIENT_ID = "dummy"
ESI_SSO_CLIENT_SECRET = "dummy"
ESI_SSO_CALLBACK_URL = "http://localhost:8000"

# By default emails are validated before new users can log in.
# It's recommended to use a free service like SparkPost or Elastic Email to send email.
# https://www.sparkpost.com/docs/integrations/django/
# https://elasticemail.com/resources/settings/smtp-api/
# Set the default from email to something like 'noreply@example.com'
# Email validation can be turned off by uncommenting the line below. This
# can break some services.
REGISTRATION_VERIFY_EMAIL = False
EMAIL_HOST = ""
EMAIL_PORT = 587
EMAIL_HOST_USER = ""
EMAIL_HOST_PASSWORD = ""
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = ""

#######################################
# Add any custom settings below here. #
#######################################

# workarounds to suppress warnings
LOGGING = None
STATICFILES_DIRS = []

from unittest.mock import Mock

# Use fakeredis for testing/linting (no Redis server required)
import fakeredis  # noqa: E402

# Create a fake Redis server instance that supports INFO command
_fake_redis_server = fakeredis.FakeServer()
_fake_redis_server.connected = True


# Monkey-patch fakeredis to support INFO command
class FakeRedisWithInfo(fakeredis.FakeStrictRedis):
    """FakeRedis with INFO command support for AllianceAuth system checks."""

    def info(self, section=None):
        """Return mock Redis INFO output."""
        return {
            "redis_version": "7.0.0",
            "redis_mode": "standalone",
            "os": "Linux",
            "arch_bits": 64,
            "multiplexing_api": "epoll",
            "process_id": 1,
            "tcp_port": 6379,
        }


# Patch django_redis to use our FakeRedisWithInfo
import django_redis  # noqa: E402
from django_redis.client import default  # noqa: E402

_original_get_client = default.DefaultClient.get_client


def _patched_get_client(self, write=True, tried=None):
    """Return FakeRedisWithInfo instead of real Redis client."""
    return FakeRedisWithInfo(server=_fake_redis_server)


default.DefaultClient.get_client = _patched_get_client

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/1",
        "OPTIONS": {
            "CONNECTION_POOL_KWARGS": {
                "connection_class": fakeredis.FakeConnection,
            },
        },
    }
}

# Silence system checks for tests
SILENCED_SYSTEM_CHECKS = [
    "allianceauth.checks.A003",
    "allianceauth.checks.B001",
    "allianceauth.checks.B002",
    "allianceauth.checks.B003",
    "allianceauth.checks.B004",
    "allianceauth.checks.B010",
    "allianceauth.checks.system_package_redis",  # Redis version check (not compatible with fakeredis)
    "esi.E003",
]
ESI_USER_CONTACT_EMAIL = "test@test.com"
