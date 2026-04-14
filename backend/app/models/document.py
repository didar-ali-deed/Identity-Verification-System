import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DocumentType(enum.StrEnum):
    PASSPORT = "passport"
    NATIONAL_ID = "national_id"
    DRIVERS_LICENSE = "drivers_license"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("idv_applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    doc_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, name="document_type", native_enum=False),
        nullable=False,
    )
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(nullable=False)
    mime_type: Mapped[str] = mapped_column(String(50), nullable=False)
    ocr_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ocr_raw_text: Mapped[str | None] = mapped_column(nullable=True)
    fraud_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    fraud_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    face_image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # God-level pipeline fields
    document_class: Mapped[str | None] = mapped_column(String(10), nullable=True)
    issuing_country: Mapped[str | None] = mapped_column(String(3), nullable=True)
    ocr_confidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    normalized_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    liveness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    liveness_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    application: Mapped["IDVApplication"] = relationship("IDVApplication", back_populates="documents")

    def __repr__(self) -> str:
        return f"<Document {self.id} type={self.doc_type}>"
