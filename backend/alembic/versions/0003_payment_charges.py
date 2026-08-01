"""Payment charges redeemable into accounts.

Revision ID: 0003_payment_charges
Revises: 0002_password_reset
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_payment_charges"
down_revision: str | None = "0002_password_reset"
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
        # The payment provider's reference, as it appears on the receipt.
        sa.Column("charge_id", sa.String(128), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        # NULL until redeemed. A timestamp rather than a boolean so a disputed
        # charge can be answered with "redeemed at", not just "redeemed".
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        # SET NULL, not CASCADE: deleting an account must not erase the record
        # that a payment was taken for it.
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    # Unique: one payment, one redeemable row. This constraint - not the
    # application check - is what ultimately stops a replayed import from
    # handing out two accounts for one payment.
    op.create_index(
        "ix_payment_charges_charge_id",
        "payment_charges",
        ["charge_id"],
        unique=True,
    )
    op.create_index("ix_payment_charges_email", "payment_charges", ["email"])
    op.create_index("ix_payment_charges_user_id", "payment_charges", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_payment_charges_user_id", table_name="payment_charges")
    op.drop_index("ix_payment_charges_email", table_name="payment_charges")
    op.drop_index("ix_payment_charges_charge_id", table_name="payment_charges")
    op.drop_table("payment_charges")
