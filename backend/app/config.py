from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "Identity Verification System"
    environment: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str = "postgresql+asyncpg://idv_user:idv_password@localhost:5432/idv_db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

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
    pipeline_mode: str = "god"  # "god", "legacy", "both"
    pipeline_pass_threshold: float = 0.87
    pipeline_review_threshold: float = 0.70
    velocity_window_hours: int = 2160  # 90 days
    velocity_max_submissions: int = 2
    ocr_confidence_threshold: float = 0.85

    # CORS
    allowed_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",")]

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
