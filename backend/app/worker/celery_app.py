"""Celery application (Redis broker + result backend)."""

from __future__ import annotations

from celery import Celery
from celery.signals import setup_logging

from app.config import settings
from app.logging_config import configure_logging

RENDER_QUEUE = "renders"
RENDER_TASK = "aseelo.render_video"

celery_app = Celery(
    "aseelo",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_default_queue=RENDER_QUEUE,
    task_routes={RENDER_TASK: {"queue": RENDER_QUEUE}},
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # One long render at a time per worker process; no speculative prefetching.
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    # Hard ceiling so a pathological input can never pin a worker forever.
    task_time_limit=60 * 60,
    task_soft_time_limit=55 * 60,
    result_expires=60 * 60 * 24,
    broker_connection_retry_on_startup=True,
    worker_max_tasks_per_child=50,
)


@setup_logging.connect
def _configure_celery_logging(**_kwargs: object) -> None:
    """Use the app's JSON logger instead of Celery's default formatter."""
    configure_logging()
