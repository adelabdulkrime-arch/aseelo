"""Flag accounts created by the guest endpoint.

Revision ID: 0004_guest_users
Revises: 0003_payment_charges
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_guest_users"
down_revision: str | None = "0003_payment_charges"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default is required: existing rows predate the column and every
    # one of them is a real account, not a guest.
    op.add_column(
        "users",
        sa.Column("is_guest", sa.Boolean(), nullable=False, server_default="false"),
    )
    # Indexed because the only queries that touch it are "how many real users
    # are there" and the pruning job, both of which filter on it.
    op.create_index("ix_users_is_guest", "users", ["is_guest"])


def downgrade() -> None:
    op.drop_index("ix_users_is_guest", table_name="users")
    op.drop_column("users", "is_guest")
