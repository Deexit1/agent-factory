"""add orgs table + org_id on every domain table (T-102 SaaS groundwork)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-06 08:05:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_ORG_ID = "default"

# Every domain table that needs org_id (docs/00-vision.md SaaS-readiness rule 1).
_TABLES = [
    "tickets",
    "ticket_events",
    "approvals",
    "agent_runs",
    "cost_ledger",
    "users",
    "escaped_defect_reports",
]


def upgrade() -> None:
    op.create_table(
        "orgs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        f"INSERT INTO orgs (id, name, created_at) VALUES ('{DEFAULT_ORG_ID}', 'Default Org', now())"
    )

    # Nullable-then-backfill-then-NOT-NULL: the safe pattern for adding a required
    # column to already-populated tables (same approach as tickets.created_at in
    # 0cf581260d39).
    for table in _TABLES:
        op.add_column(table, sa.Column("org_id", sa.String(), nullable=True))
        op.execute(f"UPDATE {table} SET org_id = '{DEFAULT_ORG_ID}'")
        op.alter_column(table, "org_id", nullable=False)
        op.create_foreign_key(
            f"fk_{table}_org_id_orgs", table, "orgs", ["org_id"], ["id"]
        )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_constraint(f"fk_{table}_org_id_orgs", table, type_="foreignkey")
        op.drop_column(table, "org_id")
    op.drop_table("orgs")
