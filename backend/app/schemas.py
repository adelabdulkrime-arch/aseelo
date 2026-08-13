"""Pydantic request/response schemas."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

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
    # Lets the UI offer "keep your work - create a real account" instead of
    # showing a guest an email address they never chose.
    is_guest: bool = False
    # The caller's own upload ceiling, in seconds. Sent because the limit
    # differs per account type: without it the UI can only discover the rule by
    # having the user upload a file and be rejected, which is the whole reason
    # a valid clip appeared to "just fail".
    max_video_duration_seconds: int | None = None
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
    # Set only on the upload response: False warns the caller that the logo has
    # no alpha channel and will render as an opaque rectangle over the video.
    logo_has_transparency: bool | None = None
    logo_cutout_applied: bool | None = None
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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def supports_captions(self) -> bool:
        """True when this template is driven by a caption track.

        Derived from the slug rather than stored, so there is one source of
        truth and no column to fall out of sync with the seeds.
        """
        from app.video.templates import CAPTION_TEMPLATE_SLUG

        return self.slug == CAPTION_TEMPLATE_SLUG


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
CaptionPosition = Literal["top", "center", "bottom"]
CaptionAnimation = Literal["none", "fade", "zoom_fade", "slide_up"]

# A caption shorter than this cannot be read; one this long is almost always a
# mistake in the timeline editor rather than an intent.
MIN_CAPTION_SECONDS = 0.3
MAX_CAPTIONS = 12


class Caption(BaseModel):
    """One timed line of text painted over the video."""

    id: str = Field(min_length=1, max_length=40)
    content: str = Field(min_length=1, max_length=200)
    start_time: float = Field(ge=0, le=600)
    end_time: float = Field(gt=0, le=600)
    position: CaptionPosition = "center"
    animation: CaptionAnimation = "fade"

    @field_validator("content")
    @classmethod
    def _clean_content(cls, value: str) -> str:
        value = "".join(ch for ch in value if ch == "\n" or ch >= " ").strip()
        if not value:
            raise ValueError("Caption text is required")
        if value.count("\n") > 3:
            raise ValueError("A caption may span at most 4 lines")
        return value

    @model_validator(mode="after")
    def _check_window(self) -> "Caption":
        if self.end_time <= self.start_time:
            raise ValueError("A caption must end after it starts")
        if self.end_time - self.start_time < MIN_CAPTION_SECONDS:
            raise ValueError(f"A caption must last at least {MIN_CAPTION_SECONDS}s")
        return self


def validate_caption_track(captions: list[Caption]) -> list[Caption]:
    """Reject a track that cannot be rendered sensibly.

    Overlap is checked per *position*: two captions in the same band would draw
    on top of each other, but a hook at the top and a CTA at the bottom running
    at the same moment is a normal design, not a conflict.
    """
    if len(captions) > MAX_CAPTIONS:
        raise ValueError(f"At most {MAX_CAPTIONS} captions are supported")

    seen_ids: set[str] = set()
    for caption in captions:
        if caption.id in seen_ids:
            raise ValueError(f"Duplicate caption id '{caption.id}'")
        seen_ids.add(caption.id)

    by_position: dict[str, list[Caption]] = {}
    for caption in captions:
        by_position.setdefault(caption.position, []).append(caption)

    for position, group in by_position.items():
        ordered = sorted(group, key=lambda c: c.start_time)
        for earlier, later in zip(ordered, ordered[1:]):
            if later.start_time < earlier.end_time:
                raise ValueError(
                    f"Captions overlap in the '{position}' band: "
                    f"'{earlier.content[:20]}' and '{later.content[:20]}'"
                )
    return captions


class VideoCreateForm(BaseModel):
    """Validated view of the multipart form used by POST /api/videos."""

    title: str | None = Field(default=None, max_length=160)
    text_content: str = Field(min_length=1, max_length=600)
    template_id: uuid.UUID
    auto_render: bool = True
    quality: Literal["fast", "balanced", "high"] = "balanced"

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
    captions: list[Caption] = Field(default_factory=list)
    quality: str = "balanced"
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

    @field_validator("captions", mode="before")
    @classmethod
    def _null_captions_to_empty(cls, value: Any) -> Any:
        # The column is NULL for every video created before timed captions, and
        # for the classic templates that never set one.
        return value or []

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


class ConvertGuestRequest(BaseModel):
    """Turn the caller's own guest session into a real account, in place.

    No `name`: a guest already has one ("Guest"), and this screen exists to
    save their work, not to collect a profile. They can rename themselves in
    Settings afterwards, same as anyone else.
    """

    email: EmailStr
    password: Password


class SetupAccountRequest(BaseModel):
    """Redeem a paid charge into an account.

    No `confirm_password`, unlike registration: the setup page shows a single
    password field, because the customer arrives here from a payment receipt
    and a second box is one more thing between them and the product. A mistyped
    password is recoverable through the ordinary reset flow.
    """

    # Both are required and both are checked: the charge reference alone does
    # not authorise account creation, the pair does.
    charge_id: str = Field(min_length=6, max_length=128)
    email: EmailStr
    password: Password


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=16, max_length=256)
    password: Password
    confirm_password: Password

    @model_validator(mode="after")
    def _passwords_match(self) -> "ResetPasswordRequest":
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self
