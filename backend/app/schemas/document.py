import uuid
from datetime import datetime

from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    doc_type: str
    original_filename: str
    file_size: int
    mime_type: str
    uploaded_at: datetime
    extracted_fields: dict | None = None  # Synchronous OCR result

    model_config = {"from_attributes": True}


class DocumentResponse(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    doc_type: str
    original_filename: str
    file_size: int
    mime_type: str
    ocr_data: dict | None = None
    ocr_raw_text: str | None = None
    fraud_score: float | None = None
    fraud_details: dict | None = None
    uploaded_at: datetime

    model_config = {"from_attributes": True}
