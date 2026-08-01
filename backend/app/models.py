"""ORM models for ASEELO Video."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class UserRole(str, enum.Enum):
    USER = "USER"
    ADMIN = "ADMIN"


class VideoStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class JobStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL_JOB_STATUSES = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------
class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role"), default=UserRole.USER, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    brand_profile: Mapped["BrandProfile | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    videos: Mapped[list["Video"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    password_reset_tokens: Mapped[list["PasswordResetToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class PasswordResetToken(Base):
    """A single-use, expiring password reset grant.

    Only the SHA-256 of the token is stored. The plaintext exists solely inside
    the email that was sent, so a database leak cannot be replayed into account
    takeovers - which is the entire point of a reset token being a bearer
    credential.
    """

    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="password_reset_tokens")


# ---------------------------------------------------------------------------
# Brand profile
# ---------------------------------------------------------------------------
class BrandProfile(TimestampMixin, Base):
    __tablename__ = "brand_profiles"
    __table_args__ = (UniqueConstraint("user_id", name="uq_brand_profiles_user_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    brand_name: Mapped[str] = mapped_column(String(120), nullable=False, default="My Brand")
    logo_url: Mapped[str | None] = mapped_column(String(1024))
    primary_color: Mapped[str] = mapped_column(String(9), nullable=False, default="#0F172A")
    secondary_color: Mapped[str] = mapped_column(String(9), nullable=False, default="#1E88E5")
    accent_color: Mapped[str] = mapped_column(String(9), nullable=False, default="#F5B700")
    font: Mapped[str] = mapped_column(String(60), nullable=False, default="noto-sans-arabic")

    phone: Mapped[str | None] = mapped_column(String(40))
    whatsapp: Mapped[str | None] = mapped_column(String(40))
    website: Mapped[str | None] = mapped_column(String(255))
    social_media: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    address: Mapped[str | None] = mapped_column(String(255))
    tagline: Mapped[str | None] = mapped_column(String(160))

    user: Mapped[User] = relationship(back_populates="brand_profile")


# ---------------------------------------------------------------------------
# Template
# ---------------------------------------------------------------------------
class Template(TimestampMixin, Base):
    __tablename__ = "templates"

    id: Mapped[uuid.UUID] = _uuid_pk()
    slug: Mapped[str] = mapped_column(String(60), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    preview_url: Mapped[str | None] = mapped_column(String(1024))
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    videos: Mapped[list["Video"]] = relationship(back_populates="template")


# ---------------------------------------------------------------------------
# Video
# ---------------------------------------------------------------------------
class Video(Base):
    __tablename__ = "videos"
    __table_args__ = (
        Index("ix_videos_user_created", "user_id", "created_at"),
        Index("ix_videos_user_status", "user_id", "status"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("templates.id", ondelete="SET NULL"), index=True
    )

    title: Mapped[str | None] = mapped_column(String(160))
    text_content: Mapped[str] = mapped_column(Text, nullable=False, default="")

    input_file_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    input_file_size: Mapped[int | None] = mapped_column(Integer)
    output_file_url: Mapped[str | None] = mapped_column(String(1024))
    output_file_size: Mapped[int | None] = mapped_column(Integer)
    thumbnail_url: Mapped[str | None] = mapped_column(String(1024))

    duration: Mapped[float | None] = mapped_column(Numeric(10, 3))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    has_audio: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    status: Mapped[VideoStatus] = mapped_column(
        SAEnum(VideoStatus, name="video_status"), default=VideoStatus.DRAFT, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    # Snapshot of the brand identity used for this render (immutable output record).
    brand_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="videos")
    template: Mapped[Template | None] = relationship(back_populates="videos")
    jobs: Mapped[list["RenderingJob"]] = relationship(
        back_populates="video",
        cascade="all, delete-orphan",
        order_by="RenderingJob.created_at.desc()",
    )

    @property
    def latest_job(self) -> "RenderingJob | None":
        return self.jobs[0] if self.jobs else None


# ---------------------------------------------------------------------------
# Rendering job
# ---------------------------------------------------------------------------
class RenderingJob(Base):
    __tablename__ = "rendering_jobs"
    __table_args__ = (Index("ix_rendering_jobs_video_created", "video_id", "created_at"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    video_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True
    )

    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus, name="job_status"), default=JobStatus.QUEUED, nullable=False, index=True
    )
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_step: Mapped[str] = mapped_column(String(60), default="upload", nullable=False)
    # Per-stage state for the frontend progress UI.
    steps: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
    celery_task_id: Mapped[str | None] = mapped_column(String(80), index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    video: Mapped[Video] = relationship(back_populates="jobs")
