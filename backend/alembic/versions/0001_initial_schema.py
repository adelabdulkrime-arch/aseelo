"""Initial ASEELO schema: users, brand profiles, templates, videos, rendering jobs.

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-31

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    user_role = sa.Enum("USER", "ADMIN", name="user_role")
    video_status = sa.Enum(
        "DRAFT", "QUEUED", "PROCESSING", "COMPLETED", "FAILED", "CANCELLED", name="video_status"
    )
    job_status = sa.Enum(
        "QUEUED", "PROCESSING", "COMPLETED", "FAILED", "CANCELLED", name="job_status"
    )

    # ---------------- users ----------------
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", user_role, nullable=False, server_default="USER"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ---------------- brand_profiles ----------------
    op.create_table(
        "brand_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_name", sa.String(120), nullable=False, server_default="My Brand"),
        sa.Column("logo_url", sa.String(1024)),
        sa.Column("primary_color", sa.String(9), nullable=False, server_default="#0F172A"),
        sa.Column("secondary_color", sa.String(9), nullable=False, server_default="#1E88E5"),
        sa.Column("accent_color", sa.String(9), nullable=False, server_default="#F5B700"),
        sa.Column("font", sa.String(60), nullable=False, server_default="noto-sans-arabic"),
        sa.Column("phone", sa.String(40)),
        sa.Column("whatsapp", sa.String(40)),
        sa.Column("website", sa.String(255)),
        sa.Column("social_media", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("address", sa.String(255)),
        sa.Column("tagline", sa.String(160)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", name="uq_brand_profiles_user_id"),
    )
    op.create_index("ix_brand_profiles_user_id", "brand_profiles", ["user_id"])

    # ---------------- templates ----------------
    op.create_table(
        "templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(60), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("preview_url", sa.String(1024)),
        sa.Column("configuration", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_templates_slug", "templates", ["slug"], unique=True)
    op.create_index("ix_templates_is_active", "templates", ["is_active"])

    # ---------------- videos ----------------
    op.create_table(
        "videos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("template_id", postgresql.UUID(as_uuid=True)),
        sa.Column("title", sa.String(160)),
        sa.Column("text_content", sa.Text(), nullable=False, server_default=""),
        sa.Column("input_file_url", sa.String(1024), nullable=False),
        sa.Column("input_file_size", sa.Integer()),
        sa.Column("output_file_url", sa.String(1024)),
        sa.Column("output_file_size", sa.Integer()),
        sa.Column("thumbnail_url", sa.String(1024)),
        sa.Column("duration", sa.Numeric(10, 3)),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("has_audio", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", video_status, nullable=False, server_default="DRAFT"),
        sa.Column("error_message", sa.Text()),
        sa.Column("brand_snapshot", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["templates.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_videos_user_id", "videos", ["user_id"])
    op.create_index("ix_videos_template_id", "videos", ["template_id"])
    op.create_index("ix_videos_user_created", "videos", ["user_id", "created_at"])
    op.create_index("ix_videos_user_status", "videos", ["user_id", "status"])

    # ---------------- rendering_jobs ----------------
    op.create_table(
        "rendering_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("video_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", job_status, nullable=False, server_default="QUEUED"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_step", sa.String(60), nullable=False, server_default="upload"),
        sa.Column("steps", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("error_message", sa.Text()),
        sa.Column("celery_task_id", sa.String(80)),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_rendering_jobs_video_id", "rendering_jobs", ["video_id"])
    op.create_index("ix_rendering_jobs_status", "rendering_jobs", ["status"])
    op.create_index("ix_rendering_jobs_celery_task_id", "rendering_jobs", ["celery_task_id"])
    op.create_index("ix_rendering_jobs_video_created", "rendering_jobs", ["video_id", "created_at"])


def downgrade() -> None:
    op.drop_table("rendering_jobs")
    op.drop_table("videos")
    op.drop_table("templates")
    op.drop_table("brand_profiles")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    sa.Enum(name="job_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="video_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=True)
