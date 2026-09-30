"""Run against a dedicated migrated Postgres database with IDV_INTEGRATION_TESTS=1."""

import os
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_db
from app.config import get_settings
from app.main import app
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.idv_application import ApplicationStatus, IDVApplication
from app.models.pipeline_result import PipelineResult
from app.models.task_outbox import TaskOutbox
from app.models.user import User, UserRole
from app.services.idv_service import IDVServiceError, create_application
from app.services.pipeline.orchestrator import run_pipeline
from app.services.pipeline.stage_9_result import run_stage_9
from app.services.pipeline.types import PipelineContext, StageResult
from app.utils.security import create_access_token

pytestmark = pytest.mark.skipif(os.getenv("IDV_INTEGRATION_TESTS") != "1", reason="Dedicated PostgreSQL required")


@pytest.fixture
async def integration():
    url = get_settings().database_url
    if "test" not in url.rsplit("/", 1)[-1]:
        pytest.fail("Integration tests require a database whose name contains 'test'")
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        users = [
            User(
                email=f"{uuid.uuid4().hex}@example.com",
                full_name="Synthetic Tester",
                password_hash="unused",
                role=role,
                is_active=True,
            )
            for role in (UserRole.USER, UserRole.USER, UserRole.ADMIN)
        ]
        db.add_all(users)
        await db.commit()
        identities = [SimpleNamespace(id=user.id, role=user.role) for user in users]

        async def override():
            try:
                yield db
                await db.commit()
            except Exception:
                await db.rollback()
                raise

        app.dependency_overrides[get_db] = override
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            try:
                yield db, client, identities
            finally:
                app.dependency_overrides.clear()
    await engine.dispose()


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}


@pytest.mark.asyncio
async def test_reset_keeps_account_and_deletes_old_inputs(integration, valid_jpeg_bytes, tmp_path, monkeypatch):
    db, client, (owner, other, _) = integration
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
    application_id = (await client.post("/api/v1/idv/submit", headers=auth(owner))).json()["id"]
    files = {"file": ("synthetic.jpg", valid_jpeg_bytes, "image/jpeg")}
    upload = await client.post(
        f"/api/v1/idv/upload-document?application_id={application_id}&doc_type=passport",
        headers=auth(owner),
        files=files,
    )
    old_doc_id = upload.json()["id"]
    doc = await db.get(Document, uuid.UUID(old_doc_id))
    old_path = tmp_path / doc.file_path
    assert old_path.exists()
    orphan = old_path.parent / "superseded-capture.jpg"
    orphan.write_bytes(valid_jpeg_bytes)
    url = f"/api/v1/idv/reset?application_id={application_id}"
    assert (await client.post(url, headers=auth(other))).status_code == 403
    response = await client.post(url, headers=auth(owner))
    assert response.status_code == 201
    assert response.json()["id"] != application_id
    assert response.json()["documents"] == []
    assert not old_path.exists()
    assert not orphan.exists()
    assert await db.scalar(select(func.count()).select_from(Document).where(Document.id == uuid.UUID(old_doc_id))) == 0
    assert (
        await db.scalar(select(func.count()).select_from(TaskOutbox).where(TaskOutbox.args[0].astext == old_doc_id))
        == 0
    )
    assert await db.get(User, owner.id) is not None


@pytest.mark.asyncio
async def test_reset_refuses_processing_and_busy_applications(integration):
    db, client, (owner, _, _) = integration
    application = await create_application(db, owner.id)
    application.status = ApplicationStatus.PROCESSING
    await db.commit()
    application_id = application.id
    url = f"/api/v1/idv/reset?application_id={application_id}"
    assert (await client.post(url, headers=auth(owner))).status_code == 409
    await db.refresh(application)
    application.status = ApplicationStatus.ERROR
    await db.commit()
    async with async_sessionmaker(db.bind)() as locked:
        await locked.execute(select(IDVApplication).where(IDVApplication.id == application_id).with_for_update())
        response = await client.post(url, headers=auth(owner))
        assert response.status_code == 409
        await locked.rollback()


@pytest.mark.asyncio
async def test_reset_removes_saved_results_and_audit(integration):
    db, client, (owner, _, _) = integration
    application = await create_application(db, owner.id)
    application_id = application.id
    await run_stage_9(
        PipelineContext(application_id=str(application_id), final_decision="REJECTED"), db, datetime.now(UTC)
    )
    await db.commit()
    response = await client.post(f"/api/v1/idv/reset?application_id={application_id}", headers=auth(owner))
    assert response.status_code == 201
    assert (
        await db.scalar(
            select(func.count()).select_from(PipelineResult).where(PipelineResult.application_id == application_id)
        )
        == 0
    )
    assert (
        await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.application_id == application_id))
        == 0
    )


@pytest.mark.asyncio
async def test_document_replacement_clears_evidence_and_blocks_stale_tasks(
    integration, valid_jpeg_bytes, tmp_path, monkeypatch
):
    import app.database
    from app.tasks.verification import _update_document_ocr

    db, client, (owner, other, _) = integration
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
    application_id = (await client.post("/api/v1/idv/submit", headers=auth(owner))).json()["id"]
    url = f"/api/v1/idv/upload-document?application_id={application_id}&doc_type=passport"
    files = {"file": ("synthetic.jpg", valid_jpeg_bytes, "image/jpeg")}
    first = (await client.post(url, headers=auth(owner), files=files)).json()["id"]
    original = await db.get(Document, uuid.UUID(first))
    original.ocr_data = {"full_name": "STALE SAMPLE"}
    await db.commit()
    replacement_url = url + "&replace_existing=true"
    assert (await client.post(replacement_url, headers=auth(other), files=files)).status_code == 403
    assert (
        await client.post(
            replacement_url, headers=auth(owner), files={"file": ("invalid.jpg", b"invalid", "image/jpeg")}
        )
    ).status_code == 422
    second = await client.post(replacement_url, headers=auth(owner), files=files)
    assert second.status_code == 201
    new_id = uuid.UUID(second.json()["id"])
    assert str(new_id) != first
    documents = (
        (await db.execute(select(Document).where(Document.application_id == uuid.UUID(application_id)))).scalars().all()
    )
    assert len(documents) == 1
    assert documents[0].ocr_data is None
    monkeypatch.setattr(app.database, "async_session_factory", async_sessionmaker(db.bind, expire_on_commit=False))
    await _update_document_ocr(first, {"full_name": "STALE SAMPLE"}, "stale")
    await db.refresh(documents[0])
    assert documents[0].ocr_data is None
    await client.post(f"/api/v1/idv/upload-selfie?application_id={application_id}", headers=auth(owner), files=files)
    assert (await client.post(replacement_url, headers=auth(owner), files=files)).status_code == 409


@pytest.mark.asyncio
async def test_ownership_and_duplicate_submission(integration, valid_jpeg_bytes):
    db, client, (owner, other, _) = integration
    response = await client.post("/api/v1/idv/submit", headers=auth(owner))
    assert response.status_code == 201
    application_id = response.json()["id"]
    duplicate = await client.post("/api/v1/idv/submit", headers=auth(owner))
    assert duplicate.status_code == 409
    unauthorized = await client.post(
        f"/api/v1/idv/upload-document?application_id={application_id}&doc_type=passport",
        headers=auth(other),
        files={"file": ("synthetic.jpg", valid_jpeg_bytes, "image/jpeg")},
    )
    assert unauthorized.status_code == 403


@pytest.mark.asyncio
async def test_uploads_commit_inputs_and_outbox_together(integration, valid_jpeg_bytes, tmp_path, monkeypatch):
    db, client, (owner, _, _) = integration
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
    application_id = (await client.post("/api/v1/idv/submit", headers=auth(owner))).json()["id"]
    url = f"/api/v1/idv/upload-document?application_id={application_id}&doc_type=passport"
    files = {"file": ("synthetic.jpg", valid_jpeg_bytes, "image/jpeg")}
    assert (await client.post(url, headers=auth(owner), files=files)).status_code == 201
    assert (await client.post(url, headers=auth(owner), files=files)).status_code == 409
    selfie = await client.post(
        f"/api/v1/idv/upload-selfie?application_id={application_id}",
        headers=auth(owner),
        files=[
            ("file", ("selfie.jpg", valid_jpeg_bytes, "image/jpeg")),
            ("frames", ("frame2.jpg", valid_jpeg_bytes, "image/jpeg")),
            ("frames", ("frame3.jpg", valid_jpeg_bytes, "image/jpeg")),
        ],
    )
    assert selfie.status_code == 201
    status = (await client.get("/api/v1/idv/status", headers=auth(owner))).json()
    assert status["selfie_uploaded"] is True
    assert status["status"] == "processing"
    jobs = (await db.execute(select(TaskOutbox).where(TaskOutbox.args[0].astext == application_id))).scalars().all()
    # Verify the pipeline job was stored, not dispatched from an uncommitted upload.
    assert any(job.task_name.endswith("run_god_pipeline") and job.dispatched_at is None for job in jobs)


@pytest.mark.asyncio
async def test_selfie_without_identity_document_is_blocked(integration, valid_jpeg_bytes):
    _, client, (owner, _, _) = integration
    application_id = (await client.post("/api/v1/idv/submit", headers=auth(owner))).json()["id"]
    response = await client.post(
        f"/api/v1/idv/upload-selfie?application_id={application_id}",
        headers=auth(owner),
        files={"file": ("synthetic.jpg", valid_jpeg_bytes, "image/jpeg")},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_only_review_ready_applications_can_be_reviewed(integration):
    db, client, (owner, _, admin) = integration
    application = await create_application(db, owner.id)
    await db.commit()
    application_id = application.id
    url = f"/api/v1/admin/applications/{application_id}"
    assert (await client.patch(url, headers=auth(owner), json={"action": "approve"})).status_code == 403
    assert (await client.patch(url, headers=auth(admin), json={"action": "approve"})).status_code == 409
    application.status = ApplicationStatus.READY_FOR_REVIEW
    await db.commit()
    assert (await client.patch(url, headers=auth(admin), json={"action": "approve"})).status_code == 200
    assert (await client.patch(url, headers=auth(admin), json={"action": "approve"})).status_code == 409
    count = await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.application_id == application_id))
    assert count == 1


@pytest.mark.asyncio
async def test_pipeline_retry_preserves_result_and_reviewer_decision(integration):
    db, _, (owner, _, admin) = integration
    application = await create_application(db, owner.id)
    ctx = PipelineContext(application_id=str(application.id), weighted_total=0.91, final_decision="MANUAL_REVIEW")
    ctx.stage_results = [StageResult(stage=index, name=str(index), passed=True) for index in range(9)]
    await run_stage_9(ctx, db, datetime.now(UTC))
    await db.commit()
    application.status = ApplicationStatus.APPROVED
    application.reviewer_id = admin.id
    await db.commit()
    repeated = await run_pipeline(str(application.id), db)
    assert repeated.final_decision == "MANUAL_REVIEW"
    assert application.status == ApplicationStatus.APPROVED
    saved = (
        await db.execute(select(PipelineResult).where(PipelineResult.application_id == application.id))
    ).scalar_one()
    assert len(saved.stage_results) == 10
    assert saved.final_decision == "MANUAL_REVIEW"


@pytest.mark.asyncio
async def test_error_application_blocks_duplicate_active_application(integration):
    db, _, (owner, _, _) = integration
    application = await create_application(db, owner.id)
    application.status = ApplicationStatus.ERROR
    await db.commit()
    with pytest.raises(IDVServiceError):
        await create_application(db, owner.id)


@pytest.mark.asyncio
async def test_outbox_dispatches_committed_jobs(integration, monkeypatch):
    import app.database
    from app.tasks import outbox

    db, _, _ = integration
    monkeypatch.setattr(app.database, "async_session_factory", async_sessionmaker(db.bind, expire_on_commit=False))
    job = TaskOutbox(task_name="synthetic.task", args=["synthetic"])
    db.add(job)
    await db.commit()
    published = []
    monkeypatch.setattr(outbox.celery_app, "send_task", lambda name, **kwargs: published.append((name, kwargs)))
    result = await outbox._dispatch()
    await db.refresh(job)
    assert result["dispatched"] >= 1
    assert job.dispatched_at is not None
    assert any(kwargs["task_id"] == str(job.id) for _, kwargs in published)


@pytest.mark.asyncio
async def test_outbox_keeps_failed_publications_for_retry(integration, monkeypatch):
    import app.database
    from app.tasks import outbox

    db, _, _ = integration
    monkeypatch.setattr(app.database, "async_session_factory", async_sessionmaker(db.bind, expire_on_commit=False))
    job = TaskOutbox(task_name="synthetic.task", args=["synthetic"])
    db.add(job)
    await db.commit()
    first = (
        await db.execute(
            select(TaskOutbox).where(TaskOutbox.dispatched_at.is_(None)).order_by(TaskOutbox.created_at).limit(1)
        )
    ).scalar_one()
    attempts = first.attempts

    def unavailable(*_, **__):
        raise ConnectionError("Synthetic broker outage")

    monkeypatch.setattr(outbox.celery_app, "send_task", unavailable)
    assert (await outbox._dispatch())["dispatched"] == 0
    await db.refresh(first)
    assert first.dispatched_at is None
    assert first.attempts == attempts + 1
