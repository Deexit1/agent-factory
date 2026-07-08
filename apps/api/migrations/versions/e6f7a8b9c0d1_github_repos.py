"""GitHub App repo registry + tickets.repo_id (T-203)

Revision ID: e6f7a8b9c0d1
Revises: d1e2f3a4b5c6
Create Date: 2026-07-08 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e6f7a8b9c0d1"
down_revision: str | None = "d1e2f3a4b5c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "repos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("mode", sa.Enum("connected", "provisioned", name="repo_mode"), nullable=False),
        sa.Column("github_installation_id", sa.BigInteger(), nullable=False),
        sa.Column("github_repo_id", sa.BigInteger(), nullable=True),
        sa.Column("github_full_name", sa.String(), nullable=True),
        sa.Column("clone_url", sa.String(), nullable=True),
        sa.Column("default_branch", sa.String(), nullable=True),
        sa.Column(
            "ci_mode",
            sa.Enum("platform_runners", "customer_ci", name="repo_ci_mode"),
            nullable=False,
        ),
        sa.Column("protected_branch_rules_verified", sa.Boolean(), nullable=False),
        sa.Column("protected_branch_rules_verified_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum("active", "disconnected", "exported", name="repo_status"),
            nullable=False,
        ),
        sa.Column("disconnected_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("disconnected_reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "github_repo_id", name="uq_repos_org_github_repo_id"),
    )

    op.add_column("tickets", sa.Column("repo_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_tickets_repo_id_repos", "tickets", "repos", ["repo_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_tickets_repo_id_repos", "tickets", type_="foreignkey")
    op.drop_column("tickets", "repo_id")
    op.drop_table("repos")
    op.execute("DROP TYPE IF EXISTS repo_status")
    op.execute("DROP TYPE IF EXISTS repo_ci_mode")
    op.execute("DROP TYPE IF EXISTS repo_mode")
