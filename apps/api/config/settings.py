from __future__ import annotations

import os
import secrets
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY") or secrets.token_urlsafe(64)

ALLOWED_HOSTS = [host for host in os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if host]


def _database_config_from_url(url: str) -> dict[str, object]:
    parsed = urlparse(url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("DATABASE_URL must be a PostgreSQL URL.")
    db_name = unquote(parsed.path.lstrip("/"))
    if not db_name:
        raise ValueError("DATABASE_URL must include a database name.")
    query_params = parse_qs(parsed.query)
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": db_name,
        "USER": unquote(parsed.username or "") or os.getenv("POSTGRES_USER", ""),
        "PASSWORD": unquote(parsed.password or "") or os.getenv("POSTGRES_PASSWORD", ""),
        "HOST": parsed.hostname or os.getenv("POSTGRES_HOST", "localhost"),
        "PORT": str(parsed.port or os.getenv("POSTGRES_PORT", "5432")),
        "OPTIONS": {k: v[0] for k, v in query_params.items() if v},
    }

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "core",
    "reports",
    "safety",
    "audit",
    "files",
    "preconstruction",
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
    "audit.middleware.AuditContextMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    DATABASES = {"default": _database_config_from_url(DATABASE_URL)}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Include built Vite app for production (collectstatic gathers it)
WEB_DIST = BASE_DIR.parent / "web" / "dist"
if WEB_DIST.exists():
    STATICFILES_DIRS = [WEB_DIST]
else:
    STATICFILES_DIRS = []

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ],
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Construction Daily Report API",
    "DESCRIPTION": "Internal API for construction daily reporting workflows.",
    "VERSION": "1.0.0",
}

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = False
# CSRF trusted origins (append production domain in env)
CSRF_TRUSTED_ORIGINS = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
] + [o for o in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

# HTTPS (enable when behind SSL reverse proxy)
if not DEBUG and os.getenv("DJANGO_SECURE_SSL_REDIRECT", "").lower() == "true":
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0") or "0")
    if SECURE_HSTS_SECONDS:
        SECURE_HSTS_INCLUDE_SUBDOMAINS = True
        SECURE_HSTS_PRELOAD = True

REPORT_ATTACHMENT_MAX_BYTES = int(os.getenv("REPORT_ATTACHMENT_MAX_BYTES", str(10 * 1024 * 1024)))
REPORT_ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "pdf"}
REPORT_ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}

# Preconstruction AI analysis provider settings
PRECONSTRUCTION_ANALYSIS_PROVIDER = os.getenv("PRECONSTRUCTION_ANALYSIS_PROVIDER", "mock").strip() or "mock"
PRECONSTRUCTION_ANALYSIS_TIMEOUT_SECONDS = int(os.getenv("PRECONSTRUCTION_ANALYSIS_TIMEOUT_SECONDS", "120") or "120")
PRECONSTRUCTION_OPENAI_API_KEY = os.getenv("PRECONSTRUCTION_OPENAI_API_KEY", "").strip()
PRECONSTRUCTION_OPENAI_BASE_URL = os.getenv("PRECONSTRUCTION_OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
PRECONSTRUCTION_OPENAI_MODEL = os.getenv("PRECONSTRUCTION_OPENAI_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini"
PRECONSTRUCTION_OPENAI_MAX_SUGGESTIONS = int(
    os.getenv("PRECONSTRUCTION_OPENAI_MAX_SUGGESTIONS", "25") or "25"
)
PRECONSTRUCTION_CAD_MAX_SUGGESTIONS = int(
    os.getenv("PRECONSTRUCTION_CAD_MAX_SUGGESTIONS", "250") or "250"
)
