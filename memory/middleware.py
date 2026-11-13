"""Row-level security (RLS) middleware setting `app.teacher_id` per request."""
from __future__ import annotations

import threading
from django.db import connection

_thread_local = threading.local()


def get_current_teacher_id() -> str | None:
    return getattr(_thread_local, "teacher_id", None)


def set_current_teacher_id(teacher_id: str | None) -> None:
    _thread_local.teacher_id = teacher_id
    if teacher_id and connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.teacher_id = %s;", [teacher_id])


class TeacherRowLevelSecurityMiddleware:
    """
    Sets the active teacher context (`app.teacher_id`) from headers, query params, or session.
    On Postgres, executes `SET LOCAL app.teacher_id` for Row-Level Security isolation.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        teacher_id = (
            request.headers.get("X-Teacher-Id")
            or request.GET.get("teacher_id")
            or request.session.get("teacher_id")
            or "teacher-wambui-ke"
        )
        request.teacher_id = teacher_id
        set_current_teacher_id(teacher_id)
        try:
            return self.get_response(request)
        finally:
            set_current_teacher_id(None)
