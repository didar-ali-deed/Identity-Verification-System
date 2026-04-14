import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PipelineResult(Base):
    __tablename__ = "pipeline_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("idv_applications.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    pipeline_version: Mapped[str] = mapped_column(String(20), default="1.0", nullable=False)

    # Stage results (JSONB for flexibility)
    stage_0_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    stage_1_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    stage_2_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    stage_3_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    stage_4_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Channel scores (Stage 5)
    channel_a_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    channel_b_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    channel_c_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    channel_d_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    channel_e_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Stage 6: weighted total
    weighted_total: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Stage 7: hard rules
    hard_rules_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    decision_override: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Stage 8: final decision
    final_decision: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Stage 9: audit data
    reason_codes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    flags: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Timestamps
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    application: Mapped["IDVApplication"] = relationship("IDVApplication", back_populates="pipeline_result")

    def __repr__(self) -> str:
        return f"<PipelineResult {self.id} decision={self.final_decision}>"
