"""Billing & metering (T-205)

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-07-09 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a2b3c4d5e6f7"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "orgs", sa.Column("plan", sa.String(), nullable=False, server_default="free")
    )
    op.add_column("orgs", sa.Column("pending_plan", sa.String(), nullable=True))
    op.add_column(
        "orgs",
        sa.Column("pending_plan_effective_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "orgs", sa.Column("current_period_end", sa.TIMESTAMP(timezone=True), nullable=True)
    )
    op.add_column(
        "orgs",
        sa.Column("billing_status", sa.String(), nullable=False, server_default="active"),
    )
    op.add_column(
        "orgs", sa.Column("dunning_grace_until", sa.TIMESTAMP(timezone=True), nullable=True)
    )
    op.add_column("orgs", sa.Column("razorpay_customer_id", sa.String(), nullable=True))
    op.add_column("orgs", sa.Column("razorpay_subscription_id", sa.String(), nullable=True))

    op.create_table(
        "usage_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("ticket_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("quantity", sa.Numeric(), nullable=False),
        sa.Column("ts", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "billing_usage_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("quantity", sa.Numeric(), nullable=False),
        sa.Column("razorpay_addon_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "org_id", "report_date", "kind", name="uq_billing_usage_reports_org_date_kind"
        ),
    )


def downgrade() -> None:
    op.drop_table("billing_usage_reports")
    op.drop_table("usage_events")
    op.drop_column("orgs", "razorpay_subscription_id")
    op.drop_column("orgs", "razorpay_customer_id")
    op.drop_column("orgs", "dunning_grace_until")
    op.drop_column("orgs", "billing_status")
    op.drop_column("orgs", "current_period_end")
    op.drop_column("orgs", "pending_plan_effective_at")
    op.drop_column("orgs", "pending_plan")
    op.drop_column("orgs", "plan")
