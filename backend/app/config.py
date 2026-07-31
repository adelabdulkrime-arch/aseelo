"""Central application settings, loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_JWT_SECRET = "insecure-development-secret-change-me"  # noqa: S105 - placeholder marker


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------- Core ----------
    app_env: Literal["development", "staging", "production", "test"] = "development"
    app_name: str = "ASEELO"
    log_level: str = "INFO"

    # ---------- Database ----------
    database_url: str = "postgresql+psycopg://aseelo:aseelo@postgres:5432/aseelo"

    # ---------- Queue ----------
    redis_url: str = "redis://redis:6379/0"

    # ---------- Security ----------
    jwt_secret: str = INSECURE_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # ---------- Storage ----------
    storage_provider: Literal["local", "s3"] = "local"
    storage_path: str = "/data/storage"
    public_media_base_url: str = "http://localhost:8000/media"
    s3_endpoint: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_bucket: str = "aseelo"
    s3_region: str = "auto"
    s3_public_base_url: str | None = None

    # ---------- Uploads ----------
    max_upload_size: int = 536_870_912  # 512 MB
    max_logo_size: int = 5_242_880  # 5 MB
    max_video_duration_seconds: int = 180
    min_video_duration_seconds: int = 1

    # ---------- FFmpeg ----------
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    output_width: int = 1080
    output_height: int = 1920
    output_fps: int = 30
    output_crf: int = 20
    output_preset: str = "medium"
    output_audio_bitrate: str = "128k"
    render_tmp_dir: str = "/data/tmp"

    # ---------- Rate limiting ----------
    rate_limit_enabled: bool = True
    auth_rate_limit: str = "10/minute"
    upload_rate_limit: str = "30/hour"

    # ---------- Misc ----------
    allowed_video_mime_types: str = (
        "video/mp4,video/quicktime,video/x-msvideo,video/x-matroska,video/webm,video/mpeg"
    )
    allowed_video_extensions: str = ".mp4,.mov,.avi,.mkv,.webm,.mpeg,.mpg,.m4v"
    allowed_image_mime_types: str = "image/png,image/jpeg,image/webp"
    allowed_image_extensions: str = ".png,.jpg,.jpeg,.webp"

    seed_admin_email: str | None = None
    seed_admin_password: str | None = None

    @field_validator("log_level")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def _production_safety(self) -> "Settings":
        """Refuse to start a production deployment with development defaults.

        Failing loudly at boot is far better than silently serving the internet
        with a publicly known signing key or a localhost CORS policy.
        """
        if self.app_env != "production":
            return self

        problems: list[str] = []
        if self.jwt_secret == INSECURE_JWT_SECRET or len(self.jwt_secret) < 32:
            problems.append(
                "JWT_SECRET is the development placeholder or too short "
                '(generate one with: python -c "import secrets;print(secrets.token_urlsafe(48))")'
            )
        if any("localhost" in origin or "127.0.0.1" in origin for origin in self.cors_origin_list):
            problems.append("CORS_ORIGINS still contains localhost; set it to your real domain")
        if "localhost" in self.public_media_base_url or "127.0.0.1" in self.public_media_base_url:
            problems.append(
                "PUBLIC_MEDIA_BASE_URL still points at localhost; browsers could not load media"
            )
        if self.storage_provider == "s3" and not (self.s3_access_key and self.s3_secret_key):
            problems.append("STORAGE_PROVIDER=s3 but S3 credentials are missing")

        if problems:
            raise ValueError(
                "Refusing to start in production:\n  - " + "\n  - ".join(problems)
            )
        return self

    # ---------- Derived helpers ----------
    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def video_mime_types(self) -> set[str]:
        return {m.strip().lower() for m in self.allowed_video_mime_types.split(",") if m.strip()}

    @property
    def video_extensions(self) -> set[str]:
        return {e.strip().lower() for e in self.allowed_video_extensions.split(",") if e.strip()}

    @property
    def image_mime_types(self) -> set[str]:
        return {m.strip().lower() for m in self.allowed_image_mime_types.split(",") if m.strip()}

    @property
    def image_extensions(self) -> set[str]:
        return {e.strip().lower() for e in self.allowed_image_extensions.split(",") if e.strip()}

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def sync_database_url(self) -> str:
        """URL usable by libpq / psycopg directly (no SQLAlchemy dialect prefix)."""
        return self.database_url.replace("postgresql+psycopg://", "postgresql://")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
