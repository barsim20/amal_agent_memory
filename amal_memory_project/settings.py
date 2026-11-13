"""Django settings for amal_memory_project."""
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(dotenv_path: Path) -> None:
    """Load key=value pairs from .env if present without overriding existing environment variables."""
    if not dotenv_path.exists():
        return
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = val


_load_dotenv(BASE_DIR / ".env")

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


def _build_database_config() -> dict:
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if db_url and "YOUR-PROJECT-REF" not in db_url:
        parsed = urlparse(db_url)
        query = parse_qs(parsed.query)
        sslmode = query.get("sslmode", ["require"])[0]
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": (parsed.path or "/postgres").lstrip("/"),
            "USER": parsed.username or "postgres",
            "PASSWORD": parsed.password or "",
            "HOST": parsed.hostname or "localhost",
            "PORT": str(parsed.port or 5432),
            "CONN_MAX_AGE": int(os.environ.get("DB_CONN_MAX_AGE", "60")),
            "OPTIONS": {"sslmode": sslmode} if sslmode else {},
        }
    db_host = os.environ.get("DB_HOST", "").strip()
    if db_host and "YOUR-PROJECT-REF" not in db_host:
        return {
            "ENGINE": os.environ.get("DB_ENGINE", "django.db.backends.postgresql"),
            "NAME": os.environ.get("DB_NAME", "postgres"),
            "USER": os.environ.get("DB_USER", "postgres"),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": db_host,
            "PORT": os.environ.get("DB_PORT", "5432"),
            "CONN_MAX_AGE": int(os.environ.get("DB_CONN_MAX_AGE", "60")),
            "OPTIONS": {"sslmode": os.environ.get("DB_SSLMODE", "require")},
        }
    return {
        "ENGINE": os.environ.get("DB_ENGINE", "django.db.backends.sqlite3"),
        "NAME": os.environ.get("DB_NAME", str(BASE_DIR / "db.sqlite3")),
    }


DATABASES = {
    "default": _build_database_config(),
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

# Claude Haiku Chat & LLM Memory Extraction Configuration
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
AMAL_CHAT_MODEL = os.environ.get("AMAL_CHAT_MODEL", "claude-3-5-haiku-latest")
AMAL_EXTRACTION_MODEL = os.environ.get("AMAL_EXTRACTION_MODEL", "claude-3-5-haiku-latest")
AMAL_DREAM_MODEL = os.environ.get("AMAL_DREAM_MODEL", "claude-3-5-haiku-latest")

# LiteLLM router model aliases
AMAL_LITELLM_ALIASES = {
    "memory-live": os.environ.get("AMAL_MODEL_LIVE", AMAL_EXTRACTION_MODEL),
    "memory-dream": os.environ.get("AMAL_MODEL_DREAM", AMAL_DREAM_MODEL),
    "memory-embed": os.environ.get("AMAL_MODEL_EMBED", "litellm/memory-embed"),
}
