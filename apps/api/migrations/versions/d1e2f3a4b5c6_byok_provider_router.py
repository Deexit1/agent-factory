"""BYOK provider keys, eval opt-ins, fallback order, agent_runs.provider (T-202)

Revision ID: d1e2f3a4b5c6
Revises: c9d0e1f2a3b4
Create Date: 2026-07-08 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: str | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_keys",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("last4", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "invalid", "revoked", name="provider_key_status"),
            nullable=False,
        ),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("rotated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "provider", name="uq_provider_keys_org_provider"),
    )

    op.create_table(
        "provider_eval_opt_ins",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("agent_role", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("opted_in_by", sa.String(), nullable=False),
        sa.Column("ts", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "agent_role", "provider", name="uq_eval_opt_in"),
    )

    op.add_column("orgs", sa.Column("llm_fallback_order", postgresql.JSONB(), nullable=True))
    op.add_column("agent_runs", sa.Column("provider", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_runs", "provider")
    op.drop_column("orgs", "llm_fallback_order")
    op.drop_table("provider_eval_opt_ins")
    op.drop_table("provider_keys")
    op.execute("DROP TYPE IF EXISTS provider_key_status")
