from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "idv_tasks",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_retry_delay=60,
    task_max_retries=3,
)

# Explicitly import task modules so Celery registers them
import app.tasks.verification  # noqa: F401, E402
