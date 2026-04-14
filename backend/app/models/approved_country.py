import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CountryStatus(enum.StrEnum):
    ACTIVE = "active"
    RESTRICTED = "restricted"
    SANCTIONED = "sanctioned"


class ApprovedCountry(Base):
    __tablename__ = "approved_countries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    country_code: Mapped[str] = mapped_column(String(3), unique=True, index=True, nullable=False)
    country_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[CountryStatus] = mapped_column(String(20), default=CountryStatus.ACTIVE, nullable=False)
    requires_edd: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<ApprovedCountry {self.country_code} status={self.status}>"
