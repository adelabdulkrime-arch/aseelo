"""Add videos.captions for timed caption tracks.

Nullable with no default: the classic templates never write it, and an existing
row must keep rendering exactly as before. `NULL` and `[]` both mean "no timed
captions, use text_content", so no backfill is needed.

Revision ID: 0007_video_captions
Revises: 0006_restore_login
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_video_captions"
down_revision: str | None = "0006_restore_login"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("captions", postgresql.JSONB(), nullable=True))
    # server_default so existing rows get 'balanced' without a separate UPDATE,
    # and so a row inserted by anything that predates this column still works.
    op.add_column(
        "videos",
        sa.Column(
            "quality",
            sa.String(16),
            nullable=False,
            server_default="balanced",
        ),
    )


def downgrade() -> None:
    op.drop_column("videos", "quality")
    op.drop_column("videos", "captions")
