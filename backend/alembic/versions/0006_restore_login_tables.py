"""Recreate password_reset_tokens and payment_charges - login is back.

Migration 0005 dropped both tables when the app went guest-only. Restoring
login re-introduced the models, so the tables have to come back.

This is a NEW forward migration rather than a downgrade to 0004, because
production is already stamped at 0005 and any other environment may be at
either revision. Running `alembic upgrade head` converges both.

The dropped rows are gone for good; 0005 did not preserve them. That is
acceptable here because both tables hold only short-lived state - reset tokens
expire within the hour, and a spent charge has already been redeemed.

Revision ID: 0006_restore_login
Revises: 0005_drop_login
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_restore_login"
down_revision: str | None = "0005_drop_login"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payment_charges",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("charge_id", sa.String(128), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index("ix_payment_charges_charge_id", "payment_charges", ["charge_id"], unique=True)
    op.create_index("ix_payment_charges_email", "payment_charges", ["email"])
    op.create_index("ix_payment_charges_user_id", "payment_charges", ["user_id"])

    op.create_table(
        "password_reset_tokens",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index(
        "ix_password_reset_tokens_token_hash", "password_reset_tokens", ["token_hash"], unique=True
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_table("password_reset_tokens")
    op.drop_table("payment_charges")
