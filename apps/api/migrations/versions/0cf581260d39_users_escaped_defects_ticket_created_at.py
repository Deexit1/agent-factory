"""users, escaped_defect_reports, tickets.created_at, drop tickets.spent_usd

Revision ID: 0cf581260d39
Revises: e9be75d61d32
Create Date: 2026-07-04 22:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0cf581260d39"
down_revision: str | None = "e9be75d61d32"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("email", sa.String(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("admin", "approver", "viewer", name="user_role"),
            nullable=False,
        ),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("email"),
    )
    op.create_table(
        "escaped_defect_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticket_id", sa.String(), nullable=False),
        sa.Column("note", sa.String(), nullable=False),
        sa.Column("reported_by", sa.String(), nullable=False),
        sa.Column("ts", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # Backfill existing rows to their (unknown) creation time = now(), so the column can be
    # NOT NULL from here on; every row created after this migration gets a real timestamp.
    op.add_column(
        "tickets",
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.alter_column("tickets", "created_at", server_default=None)

    # cost_ledger is the documented source of truth for $/ticket (docs/02-data-model.md);
    # this column was never written to and only ever read back its own default of 0.
    op.drop_column("tickets", "spent_usd")


def downgrade() -> None:
    op.add_column(
        "tickets", sa.Column("spent_usd", sa.Numeric(), nullable=False, server_default="0")
    )
    op.alter_column("tickets", "spent_usd", server_default=None)
    op.drop_column("tickets", "created_at")
    op.drop_table("escaped_defect_reports")
    op.drop_table("users")
    sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=True)
