from datetime import UTC, datetime

import structlog
from sqlalchemy import select

from app.models.task_outbox import TaskOutbox
from app.tasks import celery_app
from app.tasks.verification import _run_async

logger = structlog.get_logger()


@celery_app.task
def dispatch_outbox():
    return _run_async(_dispatch())


async def _dispatch():
    from app.database import async_session_factory

    sent = 0
    async with async_session_factory() as db:
        rows = (
            (
                await db.execute(
                    select(TaskOutbox)
                    .where(TaskOutbox.dispatched_at.is_(None))
                    .order_by(TaskOutbox.created_at)
                    .limit(50)
                    .with_for_update(skip_locked=True)
                )
            )
            .scalars()
            .all()
        )
        for job in rows:
            job.attempts += 1
            try:
                celery_app.send_task(job.task_name, args=job.args, task_id=str(job.id))
                job.dispatched_at = datetime.now(UTC)
                sent += 1
            except Exception:
                logger.warning("Task publication deferred", task=job.task_name, job_id=str(job.id))
                break
        await db.commit()
    return {"dispatched": sent}
