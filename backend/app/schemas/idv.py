import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, field_validator

from app.schemas.document import DocumentResponse


class DocumentTypeEnum(StrEnum):
    PASSPORT = "passport"
    NATIONAL_ID = "national_id"
    DRIVERS_LICENSE = "drivers_license"


class IDVSubmitRequest(BaseModel):
    document_type: DocumentTypeEnum


class IDVStatusResponse(BaseModel):
    id: uuid.UUID
    status: str
    submitted_at: datetime
    reviewed_at: datetime | None = None
    rejection_reason: str | None = None
    documents: list[DocumentResponse] = []
    face_match_score: float | None = None
    face_is_match: bool | None = None

    model_config = {"from_attributes": True}


class ApplicationListItem(BaseModel):
    id: uuid.UUID
    user_email: str
    user_full_name: str
    status: str
    submitted_at: datetime
    reviewed_at: datetime | None = None
    document_count: int = 0

    model_config = {"from_attributes": True}


class ApplicationListResponse(BaseModel):
    items: list[ApplicationListItem]
    total: int
    page: int
    page_size: int


class ApplicationDetailResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_email: str
    user_full_name: str
    status: str
    submitted_at: datetime
    reviewed_at: datetime | None = None
    rejection_reason: str | None = None
    reviewer_id: uuid.UUID | None = None
    documents: list[DocumentResponse] = []
    face_match_score: float | None = None
    face_is_match: bool | None = None

    model_config = {"from_attributes": True}


class ReviewRequest(BaseModel):
    action: str
    reason: str | None = None

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        if v not in ("approve", "reject"):
            raise ValueError("Action must be 'approve' or 'reject'")
        return v

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str | None, info) -> str | None:
        if info.data.get("action") == "reject" and (not v or len(v.strip()) < 10):
            raise ValueError("Rejection reason must be at least 10 characters")
        return v


class StatsResponse(BaseModel):
    total_applications: int
    pending: int
    processing: int
    ready_for_review: int
    approved: int
    rejected: int
    error: int
    avg_processing_hours: float | None = None
    fraud_flag_rate: float | None = None
