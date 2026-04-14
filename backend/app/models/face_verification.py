import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class FaceVerification(Base):
    __tablename__ = "face_verifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("idv_applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    selfie_path: Mapped[str] = mapped_column(String(500), nullable=False)
    document_face_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_match: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(50), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    application: Mapped["IDVApplication"] = relationship("IDVApplication", back_populates="face_verifications")

    def __repr__(self) -> str:
        return f"<FaceVerification {self.id} match={self.is_match}>"
