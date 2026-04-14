"""Core data structures for the God-Level pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StageResult:
    """Result of a single pipeline stage."""

    stage: int
    name: str
    passed: bool
    hard_fail: bool = False
    details: dict = field(default_factory=dict)
    flags: list[dict] = field(default_factory=list)
    reason_codes: list[dict] = field(default_factory=list)
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "name": self.name,
            "passed": self.passed,
            "hard_fail": self.hard_fail,
            "details": self.details,
            "flags": self.flags,
            "reason_codes": self.reason_codes,
            "duration_ms": round(self.duration_ms, 2),
        }


@dataclass
class ExtractedFields:
    """Unified field container for a single document zone."""

    full_name: str | None = None
    father_name: str | None = None
    dob: str | None = None  # YYYYMMDD canonical after normalization
    expiry_date: str | None = None  # YYYYMMDD
    document_number: str | None = None
    national_id_number: str | None = None
    nationality: str | None = None
    gender: str | None = None
    place_of_birth: str | None = None
    issuing_authority: str | None = None
    date_of_issue: str | None = None
    address: str | None = None
    # Per-field OCR confidence scores
    confidences: dict[str, float] = field(default_factory=dict)
    # Source tag: "passport_mrz", "passport_viz", "id_front", "id_back_mrz"
    source: str = ""

    def to_dict(self) -> dict:
        return {
            k: v
            for k, v in {
                "full_name": self.full_name,
                "father_name": self.father_name,
                "dob": self.dob,
                "expiry_date": self.expiry_date,
                "document_number": self.document_number,
                "national_id_number": self.national_id_number,
                "nationality": self.nationality,
                "gender": self.gender,
                "place_of_birth": self.place_of_birth,
                "issuing_authority": self.issuing_authority,
                "date_of_issue": self.date_of_issue,
                "address": self.address,
                "confidences": self.confidences,
                "source": self.source,
            }.items()
            if v is not None and v != "" and v != {}
        }


@dataclass
class PipelineContext:
    """Mutable context passed through all pipeline stages, accumulating results."""

    application_id: str

    # Input paths
    passport_image_path: str | None = None
    id_image_path: str | None = None
    selfie_image_path: str | None = None

    # Document classification (Stage 0)
    passport_doc_class: str | None = None  # "TD3"
    id_doc_class: str | None = None  # "TD1" or "TD2"
    passport_country: str | None = None
    id_country: str | None = None

    # Extracted fields (Stage 2)
    passport_mrz_fields: ExtractedFields | None = None
    passport_viz_fields: ExtractedFields | None = None
    id_front_fields: ExtractedFields | None = None
    id_back_mrz_fields: ExtractedFields | None = None

    # Normalized / merged fields (Stage 3)
    normalized_passport: dict | None = None
    normalized_id: dict | None = None

    # Face crop paths
    passport_face_path: str | None = None
    id_face_path: str | None = None

    # OCR raw results (for confidence mapping)
    passport_ocr_results: list[dict] = field(default_factory=list)
    id_ocr_results: list[dict] = field(default_factory=list)
    passport_raw_text: str = ""
    id_raw_text: str = ""

    # Stage results accumulator
    stage_results: list[StageResult] = field(default_factory=list)

    # Channel scores (Stage 5)
    channel_scores: dict[str, float] = field(default_factory=dict)

    # Weighted total (Stage 6)
    weighted_total: float = 0.0

    # Hard rule override (Stage 7)
    decision_override: str | None = None  # "hard_reject" or "manual_review"

    # Final decision (Stage 8)
    final_decision: str | None = None

    # Accumulated flags and reason codes
    flags: list[dict] = field(default_factory=list)
    reason_codes: list[dict] = field(default_factory=list)

    # Self-reported form data (future)
    form_data: dict | None = None

    # Document DB IDs for updates
    passport_doc_id: str | None = None
    id_doc_id: str | None = None

    def add_flag(self, flag_type: str, stage: int, detail: str) -> None:
        self.flags.append({"flag_type": flag_type, "stage": stage, "detail": detail})

    def add_reason_code(self, code: str, stage: int, severity: str, message: str) -> None:
        self.reason_codes.append({"code": code, "stage": stage, "severity": severity, "message": message})
