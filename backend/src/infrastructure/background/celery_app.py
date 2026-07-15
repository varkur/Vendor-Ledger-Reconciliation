"""
Celery application configuration.

Configures the Celery app with Redis as the message broker and result backend.
All VLR async tasks (SAP extraction, reconciliation engine, notifications)
are dispatched through this Celery instance.
"""

from celery import Celery

from src.config.settings import settings

celery_app = Celery(
    "vlr_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=getattr(settings, 'CELERY_RESULT_BACKEND', settings.CELERY_BROKER_URL),
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
    # Task result expiration (24 hours)
    result_expires=86400,
)

# Auto-discover tasks from VLR task modules
celery_app.autodiscover_tasks(
    [
        "src.infrastructure.tasks.vlr",
    ]
)
