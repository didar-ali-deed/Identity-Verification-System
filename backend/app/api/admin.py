import uuid
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_admin, get_db
from app.config import get_settings
from app.models.approved_country import ApprovedCountry
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.document_class_rule import DocumentClassRule
from app.models.idv_application import ApplicationStatus, IDVApplication
from app.models.user import User
from app.models.watchlist_entry import WatchlistEntry
from app.schemas.idv import (
    ApplicationListItem,
    ApplicationListResponse,
    ReviewRequest,
    StatsResponse,
)
from app.schemas.pipeline import (
    ApprovedCountryCreate,
    ApprovedCountryResponse,
    DocumentClassRuleCreate,
    DocumentClassRuleResponse,
    WatchlistEntryCreate,
    WatchlistEntryResponse,
)

settings = get_settings()
logger = structlog.get_logger()
router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/applications", response_model=ApplicationListResponse)
async def list_applications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> dict:
    query = select(IDVApplication).options(
        selectinload(IDVApplication.user),
        selectinload(IDVApplication.documents),
    )

    if status:
        try:
            status_enum = ApplicationStatus(status)
            query = query.where(IDVApplication.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid status: {status}") from None

    # Count total
    count_query = select(func.count()).select_from(IDVApplication)
    if status:
        count_query = count_query.where(IDVApplication.status == ApplicationStatus(status))
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    query = query.order_by(IDVApplication.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    applications = result.scalars().all()

    items = []
    for app in applications:
        items.append(
            ApplicationListItem(
                id=app.id,
                user_email=app.user.email,
                user_full_name=app.user.full_name,
                status=app.status.value,
                submitted_at=app.submitted_at,
                reviewed_at=app.reviewed_at,
                document_count=len(app.documents),
            )
        )

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/applications/{application_id}")
async def get_application_detail(
    application_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> dict:
    result = await db.execute(
        select(IDVApplication)
        .where(IDVApplication.id == application_id)
        .options(
            selectinload(IDVApplication.user),
            selectinload(IDVApplication.documents),
            selectinload(IDVApplication.face_verifications),
            selectinload(IDVApplication.pipeline_result),
        )
    )
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    face_score = None
    face_match = None
    if application.face_verifications:
        latest = application.face_verifications[-1]
        face_score = latest.similarity_score
        face_match = latest.is_match

    # Build pipeline result if available
    pipeline_data = None
    if application.pipeline_result:
        pr = application.pipeline_result
        pipeline_data = {
            "id": pr.id,
            "pipeline_version": pr.pipeline_version,
            "stage_0_result": pr.stage_0_result,
            "stage_1_result": pr.stage_1_result,
            "stage_2_result": pr.stage_2_result,
            "stage_3_result": pr.stage_3_result,
            "stage_4_result": pr.stage_4_result,
            "channel_scores": {
                "channel_a": pr.channel_a_score,
                "channel_b": pr.channel_b_score,
                "channel_c": pr.channel_c_score,
                "channel_d": pr.channel_d_score,
                "channel_e": pr.channel_e_score,
            },
            "weighted_total": pr.weighted_total,
            "hard_rules_result": pr.hard_rules_result,
            "decision_override": pr.decision_override,
            "final_decision": pr.final_decision,
            "reason_codes": pr.reason_codes,
            "flags": pr.flags,
            "started_at": pr.started_at,
            "completed_at": pr.completed_at,
        }

    return {
        "id": application.id,
        "user_id": application.user_id,
        "user_email": application.user.email,
        "user_full_name": application.user.full_name,
        "status": application.status.value,
        "submitted_at": application.submitted_at,
        "reviewed_at": application.reviewed_at,
        "rejection_reason": application.rejection_reason,
        "reviewer_id": application.reviewer_id,
        "documents": application.documents,
        "face_match_score": face_score,
        "face_is_match": face_match,
        "pipeline_version": application.pipeline_version,
        "pipeline_decision": application.pipeline_decision,
        "verification_score": application.verification_score,
        "score_details": application.score_details,
        "pipeline_result": pipeline_data,
    }


@router.patch("/applications/{application_id}")
async def review_application(
    application_id: uuid.UUID,
    request: ReviewRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> dict:
    result = await db.execute(select(IDVApplication).where(IDVApplication.id == application_id))
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    if application.status not in (
        ApplicationStatus.READY_FOR_REVIEW,
        ApplicationStatus.PENDING,
        ApplicationStatus.PROCESSING,
    ):
        raise HTTPException(
            status_code=409,
            detail=f"Application cannot be reviewed in '{application.status.value}' state",
        )

    now = datetime.now(UTC)
    previous_status = application.status.value

    if request.action == "approve":
        application.status = ApplicationStatus.APPROVED
        application.reviewed_at = now
        application.reviewer_id = admin.id
        application.rejection_reason = None
    elif request.action == "reject":
        application.status = ApplicationStatus.REJECTED
        application.reviewed_at = now
        application.reviewer_id = admin.id
        application.rejection_reason = request.reason

    # Create audit log
    audit_log = AuditLog(
        application_id=application_id,
        action=f"application_{request.action}d",
        performed_by=admin.id,
        details={
            "action": request.action,
            "reason": request.reason,
            "previous_status": previous_status,
        },
    )
    db.add(audit_log)
    await db.flush()

    await logger.ainfo(
        "Application reviewed",
        application_id=str(application_id),
        action=request.action,
        reviewer=str(admin.id),
    )

    return {
        "id": application.id,
        "status": application.status.value,
        "reviewed_at": application.reviewed_at,
        "reviewer_id": application.reviewer_id,
        "message": f"Application {request.action}d successfully",
    }


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> dict:
    # Count by status
    status_counts = {}
    for status in ApplicationStatus:
        result = await db.execute(
            select(func.count()).select_from(IDVApplication).where(IDVApplication.status == status)
        )
        status_counts[status.value] = result.scalar() or 0

    total = sum(status_counts.values())

    # Average processing time (submitted to reviewed)
    avg_time_result = await db.execute(
        select(func.avg(func.extract("epoch", IDVApplication.reviewed_at - IDVApplication.submitted_at))).where(
            IDVApplication.reviewed_at.isnot(None)
        )
    )
    avg_seconds = avg_time_result.scalar()
    avg_hours = round(avg_seconds / 3600, 2) if avg_seconds else None

    # Fraud flag rate
    flagged_result = await db.execute(
        select(func.count()).select_from(Document).where(Document.fraud_score >= settings.fraud_score_threshold)
    )
    flagged_count = flagged_result.scalar() or 0
    total_docs_result = await db.execute(
        select(func.count()).select_from(Document).where(Document.fraud_score.isnot(None))
    )
    total_docs = total_docs_result.scalar() or 0
    fraud_rate = round(flagged_count / total_docs, 4) if total_docs > 0 else None

    return {
        "total_applications": total,
        "pending": status_counts.get("pending", 0),
        "processing": status_counts.get("processing", 0),
        "ready_for_review": status_counts.get("ready_for_review", 0),
        "approved": status_counts.get("approved", 0),
        "rejected": status_counts.get("rejected", 0),
        "error": status_counts.get("error", 0),
        "avg_processing_hours": avg_hours,
        "fraud_flag_rate": fraud_rate,
    }


# ============================
# Pipeline Config CRUD
# ============================


# --- Approved Countries ---


@router.get("/pipeline/countries", response_model=list[ApprovedCountryResponse])
async def list_countries(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> list:
    result = await db.execute(select(ApprovedCountry).order_by(ApprovedCountry.country_code))
    return list(result.scalars().all())


@router.post("/pipeline/countries", response_model=ApprovedCountryResponse, status_code=201)
async def create_country(
    body: ApprovedCountryCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> ApprovedCountry:
    country = ApprovedCountry(
        country_code=body.country_code.upper(),
        country_name=body.country_name,
        status=body.status,
        requires_edd=body.requires_edd,
    )
    db.add(country)
    await db.flush()
    await db.refresh(country)
    return country


@router.delete("/pipeline/countries/{country_code}", status_code=204)
async def delete_country(
    country_code: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> None:
    result = await db.execute(select(ApprovedCountry).where(ApprovedCountry.country_code == country_code.upper()))
    country = result.scalar_one_or_none()
    if not country:
        raise HTTPException(status_code=404, detail="Country not found")
    await db.delete(country)
    await db.flush()


# --- Document Class Rules ---


@router.get("/pipeline/rules", response_model=list[DocumentClassRuleResponse])
async def list_rules(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> list:
    result = await db.execute(select(DocumentClassRule).order_by(DocumentClassRule.country_code))
    return list(result.scalars().all())


@router.post("/pipeline/rules", response_model=DocumentClassRuleResponse, status_code=201)
async def create_rule(
    body: DocumentClassRuleCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> DocumentClassRule:
    rule = DocumentClassRule(
        country_code=body.country_code.upper(),
        document_class=body.document_class.upper(),
        application_type=body.application_type,
        is_required=body.is_required,
        is_allowed=body.is_allowed,
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    return rule


@router.delete("/pipeline/rules/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> None:
    result = await db.execute(select(DocumentClassRule).where(DocumentClassRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    await db.delete(rule)
    await db.flush()


# --- Watchlist ---


@router.get("/pipeline/watchlist", response_model=list[WatchlistEntryResponse])
async def list_watchlist(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> list:
    result = await db.execute(
        select(WatchlistEntry).where(WatchlistEntry.is_active.is_(True)).order_by(WatchlistEntry.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/pipeline/watchlist", response_model=WatchlistEntryResponse, status_code=201)
async def create_watchlist_entry(
    body: WatchlistEntryCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> WatchlistEntry:
    entry = WatchlistEntry(
        id_number=body.id_number,
        full_name=body.full_name,
        reason=body.reason,
        source=body.source,
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


@router.delete("/pipeline/watchlist/{entry_id}", status_code=204)
async def deactivate_watchlist_entry(
    entry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> None:
    result = await db.execute(select(WatchlistEntry).where(WatchlistEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Watchlist entry not found")
    entry.is_active = False
    await db.flush()
