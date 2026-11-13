"""Django settings for amal_memory_project."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "amal-memory-dev-secret-key-change-in-production",
)

DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() == "true"

ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "memory.apps.MemoryConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "memory.middleware.TeacherRowLevelSecurityMiddleware",
]

ROOT_URLCONF = "amal_memory_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "amal_memory_project.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": os.environ.get("DB_ENGINE", "django.db.backends.sqlite3"),
        "NAME": os.environ.get("DB_NAME", str(BASE_DIR / "db.sqlite3")),
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "amal-memory-cache",
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Celery settings (eager by default in local/test environments)
CELERY_TASK_ALWAYS_EAGER = os.environ.get("CELERY_TASK_ALWAYS_EAGER", "true").lower() == "true"
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "memory://")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "cache+memory://")

# Amal Memory & Dreaming configuration
AMAL_MEMORY_TOMBSTONE_SECRET = os.environ.get(
    "AMAL_MEMORY_TOMBSTONE_SECRET",
    "amal-tombstone-hmac-key-2026",
)
AMAL_EMBED_MODEL = os.environ.get("AMAL_EMBED_MODEL", "AfriE5-Large-Instruct-halfvec1024")
AMAL_EMBED_DIM = 1024

# Staged taxonomy rollout: "phase2_propose_only" | "phase3_low_risk_auto" | "phase3_full_auto"
AMAL_TAXONOMY_STAGE = os.environ.get("AMAL_TAXONOMY_STAGE", "phase3_full_auto")

# LiteLLM router model aliases
AMAL_LITELLM_ALIASES = {
    "memory-live": os.environ.get("AMAL_MODEL_LIVE", "litellm/memory-live"),
    "memory-dream": os.environ.get("AMAL_MODEL_DREAM", "litellm/memory-dream"),
    "memory-embed": os.environ.get("AMAL_MODEL_EMBED", "litellm/memory-embed"),
}
