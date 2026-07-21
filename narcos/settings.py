"""Narcos settings — spec §1, §15; database per D66 (PostgreSQL, localhost)."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "NARCOS_SECRET_KEY", "dev-only-insecure-key-change-in-production"
)
DEBUG = os.environ.get("NARCOS_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("NARCOS_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")


def _csrf_trusted_origins():
    """Full origins Django will trust for unsafe requests (D83).

    Behind a proxy or when the browser reaches us by a name/scheme Django
    doesn't itself see, CSRF needs the origin spelled out with a scheme.
    Deriving them from ALLOWED_HOSTS means the deployment sets the static IP
    once; an explicit NARCOS_CSRF_TRUSTED_ORIGINS overrides when needed.
    """
    explicit = os.environ.get("NARCOS_CSRF_TRUSTED_ORIGINS", "").strip()
    if explicit:
        return [o.strip() for o in explicit.split(",") if o.strip()]
    origins = []
    for host in ALLOWED_HOSTS:
        host = host.strip()
        if not host or host == "*" or host.startswith("."):
            continue  # wildcards aren't valid origins
        origins.append(f"http://{host}")
        origins.append(f"https://{host}")  # so a future TLS proxy needs no change
    return origins


CSRF_TRUSTED_ORIGINS = _csrf_trusted_origins()

# The on-prem stack serves plain HTTP directly (no proxy), so proxy-header
# trust and HTTPS-only cookies stay OFF — enabling them here would let a
# client spoof the scheme, or stop the login cookie from ever being sent.
# Flip NARCOS_BEHIND_TLS_PROXY=1 only when a TLS-terminating proxy is added.
if os.environ.get("NARCOS_BEHIND_TLS_PROXY", "0") == "1":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "catalog",
    "stock",
    "docs",
    "money",
    "reports",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "narcos.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "narcos.wsgi.application"

# D66: PostgreSQL, localhost only (R45). Password from env in production;
# the default below is the local dev role only.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("NARCOS_DB_NAME", "narcos"),
        "USER": os.environ.get("NARCOS_DB_USER", "narcos"),
        "PASSWORD": os.environ.get("NARCOS_DB_PASSWORD", "narcos-dev"),
        "HOST": os.environ.get("NARCOS_DB_HOST", "localhost"),
        "PORT": os.environ.get("NARCOS_DB_PORT", "5432"),
    }
}

AUTH_USER_MODEL = "core.User"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English")]  # D56: Tigrigna/Amharic are future additions
USE_I18N = True
TIME_ZONE = "Africa/Addis_Ababa"  # R11
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STATIC_ROOT.mkdir(exist_ok=True)  # whitenoise warns if it doesn't exist
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
