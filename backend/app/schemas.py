"""Pydantic request/response schemas."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models import JobStatus, UserRole, VideoStatus

HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")

Password = Annotated[str, Field(min_length=8, max_length=128)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: Password
    confirm_password: Password

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Name must be at least 2 characters")
        return value

    @model_validator(mode="after")
    def _passwords_match(self) -> "RegisterRequest":
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(ORMModel):
    id: uuid.UUID
    name: str
    email: EmailStr
    role: UserRole
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - an OAuth token type, not a secret
    expires_in: int
    user: UserOut


# ---------------------------------------------------------------------------
# Brand
# ---------------------------------------------------------------------------
class BrandUpdate(BaseModel):
    brand_name: str | None = Field(default=None, min_length=1, max_length=120)
    primary_color: str | None = None
    secondary_color: str | None = None
    accent_color: str | None = None
    font: str | None = Field(default=None, max_length=60)
    phone: str | None = Field(default=None, max_length=40)
    whatsapp: str | None = Field(default=None, max_length=40)
    website: str | None = Field(default=None, max_length=255)
    social_media: dict[str, str] | None = None
    address: str | None = Field(default=None, max_length=255)
    tagline: str | None = Field(default=None, max_length=160)

    @field_validator("primary_color", "secondary_color", "accent_color")
    @classmethod
    def _valid_color(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not HEX_COLOR.match(value):
            raise ValueError("Color must be a hex value such as #1E88E5")
        return value.upper()

    @field_validator("website")
    @classmethod
    def _normalise_website(cls, value: str | None) -> str | None:
        if not value:
            return None
        value = value.strip()
        if value and not re.match(r"^https?://", value, re.IGNORECASE):
            value = f"https://{value}"
        return value

    @field_validator("social_media")
    @classmethod
    def _limit_social(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        if value is None:
            return None
        if len(value) > 12:
            raise ValueError("At most 12 social media entries are supported")
        cleaned = {}
        for key, val in value.items():
            if not isinstance(val, str) or len(val) > 255 or len(key) > 40:
                raise ValueError("Invalid social media entry")
            if val.strip():
                cleaned[key.strip().lower()] = val.strip()
        return cleaned


class BrandOut(ORMModel):
    id: uuid.UUID
    brand_name: str
    logo_url: str | None
    primary_color: str
    secondary_color: str
    accent_color: str
    font: str
    phone: str | None
    whatsapp: str | None
    website: str | None
    social_media: dict[str, Any]
    address: str | None
    tagline: str | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
class TemplateOut(ORMModel):
    id: uuid.UUID
    slug: str
    name: str
    description: str | None
    preview_url: str | None
    configuration: dict[str, Any]
    is_active: bool
    sort_order: int


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------
class JobStepOut(BaseModel):
    key: str
    label: str
    label_ar: str
    status: str  # pending | active | done | failed
    progress: int = 0


class JobOut(ORMModel):
    id: uuid.UUID
    video_id: uuid.UUID
    status: JobStatus
    progress: int
    current_step: str
    error_message: str | None
    attempt: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    steps: list[JobStepOut] = Field(default_factory=list)

    @field_validator("steps", mode="before")
    @classmethod
    def _steps_from_jsonb(cls, value: Any) -> Any:
        """The DB stores steps as a JSONB object; expose an ordered list."""
        if isinstance(value, dict):
            return list(value.get("items", []))
        return value or []


# ---------------------------------------------------------------------------
# Videos
# ---------------------------------------------------------------------------
class VideoCreateForm(BaseModel):
    """Validated view of the multipart form used by POST /api/videos."""

    title: str | None = Field(default=None, max_length=160)
    text_content: str = Field(min_length=1, max_length=600)
    template_id: uuid.UUID
    auto_render: bool = True

    @field_validator("text_content")
    @classmethod
    def _clean_text(cls, value: str) -> str:
        # Strip control characters that would break the text renderer, keep newlines.
        value = "".join(ch for ch in value if ch == "\n" or ch >= " ")
        value = value.strip()
        if not value:
            raise ValueError("Text content is required")
        if value.count("\n") > 9:
            raise ValueError("At most 10 lines of text are supported")
        return value

    @field_validator("title")
    @classmethod
    def _clean_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class VideoOut(ORMModel):
    id: uuid.UUID
    title: str | None
    text_content: str
    template_id: uuid.UUID | None
    status: VideoStatus
    output_file_url: str | None
    thumbnail_url: str | None
    duration: float | None
    width: int | None
    height: int | None
    has_audio: bool
    output_file_size: int | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None
    template: TemplateOut | None = None
    job: JobOut | None = None

    @field_validator("duration", mode="before")
    @classmethod
    def _decimal_to_float(cls, value: Any) -> Any:
        return float(value) if value is not None else None


class VideoListOut(BaseModel):
    items: list[VideoOut]
    total: int
    page: int
    page_size: int


class DashboardStats(BaseModel):
    total_videos: int
    videos_today: int
    processing_jobs: int
    completed_videos: int
    failed_videos: int
    storage_used_bytes: int
    recent_videos: list[VideoOut]


class MessageResponse(BaseModel):
    message: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr
