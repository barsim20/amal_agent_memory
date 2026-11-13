"""Celery configuration for Amal Memory and Dreaming."""
import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "amal_memory_project.settings")

app = Celery("amal_memory_project")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "nightly-dreaming-fanout": {
        "task": "memory.tasks.run_nightly_dream_fanout",
        "schedule": crontab(hour=2, minute=0),
    },
    "expire-stale-consent-requests": {
        "task": "memory.tasks.expire_stale_consent_requests",
        "schedule": crontab(hour=3, minute=0),
    },
}
