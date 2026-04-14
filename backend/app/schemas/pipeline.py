"""Pydantic schemas for the God-Level pipeline API endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel

# --- Config CRUD schemas ---


class ApprovedCountryCreate(BaseModel):
    country_code: str
    country_name: str
    status: str = "active"
    requires_edd: bool = False


class ApprovedCountryResponse(BaseModel):
    id: uuid.UUID
    country_code: str
    country_name: str
    status: str
    requires_edd: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentClassRuleCreate(BaseModel):
    country_code: str
    document_class: str
    application_type: str = "idv_standard"
    is_required: bool = False
    is_allowed: bool = True


class DocumentClassRuleResponse(BaseModel):
    id: uuid.UUID
    country_code: str
    document_class: str
    application_type: str
    is_required: bool
    is_allowed: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class WatchlistEntryCreate(BaseModel):
    id_number: str
    full_name: str | None = None
    reason: str
    source: str = "manual"


class WatchlistEntryResponse(BaseModel):
    id: uuid.UUID
    id_number: str
    full_name: str | None
    reason: str
    source: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Pipeline result schemas ---


class PipelineStageResult(BaseModel):
    stage: int
    name: str
    passed: bool
    hard_fail: bool = False
    details: dict = {}
    flags: list[dict] = []
    reason_codes: list[dict] = []
    duration_ms: float = 0.0


class PipelineChannelScores(BaseModel):
    channel_a: float | None = None
    channel_b: float | None = None
    channel_c: float | None = None
    channel_d: float | None = None
    channel_e: float | None = None


class PipelineResultResponse(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    pipeline_version: str
    stage_0_result: dict | None = None
    stage_1_result: dict | None = None
    stage_2_result: dict | None = None
    stage_3_result: dict | None = None
    stage_4_result: dict | None = None
    channel_scores: PipelineChannelScores | None = None
    weighted_total: float | None = None
    hard_rules_result: dict | None = None
    decision_override: str | None = None
    final_decision: str | None = None
    reason_codes: list | None = None
    flags: list | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}
