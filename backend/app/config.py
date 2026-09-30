from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Identity Verification System"
    environment: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str = "postgresql+asyncpg://idv_user:idv_password@localhost:55432/idv_db"

    # Redis
    redis_url: str = "redis://localhost:56379/0"

    # JWT
    jwt_secret_key: str = "change-me-generate-with-openssl-rand-hex-32"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # File Uploads
    upload_dir: str = "./uploads"
    max_file_size_mb: int = 10

    # Verification Thresholds
    face_similarity_threshold: float = 0.6
    fraud_score_threshold: float = 0.7

    # God-Level Pipeline
    pipeline_mode: Literal["god"] = "god"
    pipeline_pass_threshold: float = 0.90
    pipeline_review_threshold: float = 0.75
    velocity_window_hours: int = 2160  # 90 days
    velocity_max_submissions: int = 2
    ocr_confidence_threshold: float = 0.85
    ocr_backend: Literal["easyocr"] = "easyocr"
    inference_use_gpu: bool = False
    face_backend: Literal["deepface", "insightface"] = "deepface"
    face_model: str = "Facenet"
    liveness_backend: Literal["heuristic", "minifasnet"] = "heuristic"
    liveness_threshold: float = 0.75
    silent_face_repo: str = "./third_party/Silent-Face-Anti-Spoofing"
    silent_face_model_dir: str = "./third_party/Silent-Face-Anti-Spoofing/resources/anti_spoof_models"

    # CORS
    allowed_origins: str = "http://localhost:5173,http://localhost:3000"

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if not 0 <= self.pipeline_review_threshold < self.pipeline_pass_threshold <= 1:
            raise ValueError("Pipeline thresholds must satisfy 0 <= review < pass <= 1")
        if not 0 < self.liveness_threshold <= 1 or not 0 < self.ocr_confidence_threshold <= 1:
            raise ValueError("Liveness and OCR thresholds must be in (0, 1]")
        if self.is_production:
            if self.debug:
                raise ValueError("DEBUG must be false in production")
            if len(self.jwt_secret_key) < 32 or self.jwt_secret_key.casefold().startswith(
                ("change-me", "replace-with")
            ):
                raise ValueError("Production requires a unique JWT_SECRET_KEY of at least 32 characters")
        return self

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",")]

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @property
    def is_production(self) -> bool:
        return self.environment.casefold() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
