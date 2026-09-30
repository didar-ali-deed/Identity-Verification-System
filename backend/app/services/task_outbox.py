from app.models.task_outbox import TaskOutbox


def enqueue(db, task_name: str, *args) -> None:
    db.add(TaskOutbox(task_name=task_name, args=list(args)))
