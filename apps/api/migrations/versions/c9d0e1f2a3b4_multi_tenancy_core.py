"""multi-tenancy core: org_members, org_invites, staff_audit_log (T-201/SPEC-201)

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-07-08 10:05:00.000000

Role moves from a single global `users.role`/`users.org_id` pair to one
`org_members` row per (org, user) — a user's role is per-org now. Existing users are
backfilled into `org_members` for the org they were already in (admin->owner,
approver->approver, viewer->viewer), then the old columns are dropped. `user_role`
already exists as a type (0cf581260d39, extended with owner/member in b8c9d0e1f2a3) —
every reference to it here uses `create_type=False` so this migration doesn't try to
create it a second time.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_USER_ROLE = postgresql.ENUM(
    "owner", "approver", "member", "viewer", name="user_role", create_type=False
)


def upgrade() -> None:
    op.add_column("orgs", sa.Column("max_parallel_tickets", sa.Integer(), nullable=True))
    op.add_column(
        "users",
        sa.Column("is_platform_staff", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "org_members",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("user_email", sa.String(), nullable=False),
        sa.Column("role", _USER_ROLE, nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"]),
        sa.ForeignKeyConstraint(["user_email"], ["users.email"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "user_email", name="uq_org_members_org_user"),
    )

    # Backfill: every existing user keeps the role they already had (admin -> owner,
    # the T-201 rename; approver/viewer unchanged) in the org they were already in.
    op.execute(
        """
        INSERT INTO org_members (org_id, user_email, role, created_at)
        SELECT org_id, email,
               (CASE WHEN role = 'admin' THEN 'owner' ELSE role::text END)::user_role,
               now()
        FROM users
        """
    )

    op.create_table(
        "org_invites",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("role", _USER_ROLE, nullable=False),
        sa.Column("invited_by", sa.String(), nullable=False),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "accepted", "revoked", name="org_invite_status"),
            nullable=False,
        ),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("accepted_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )

    op.create_table(
        "staff_audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("staff_email", sa.String(), nullable=False),
        sa.Column("org_id", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("path", sa.String(), nullable=True),
        sa.Column("ts", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.drop_constraint("fk_users_org_id_orgs", "users", type_="foreignkey")
    op.drop_column("users", "role")
    op.drop_column("users", "org_id")


def downgrade() -> None:
    # Shape-reversible, not lossless (matches this repo's own convention for
    # enum/membership migrations, e.g. e5f6a7b8c9d0's downgrade) — restored users get
    # the single default org at the viewer role, not a reconstructed per-org history.
    op.add_column("users", sa.Column("org_id", sa.String(), nullable=True))
    op.add_column("users", sa.Column("role", _USER_ROLE, nullable=True))
    op.execute("UPDATE users SET org_id = 'default', role = 'viewer'")
    op.alter_column("users", "org_id", nullable=False)
    op.alter_column("users", "role", nullable=False)
    op.create_foreign_key("fk_users_org_id_orgs", "users", "orgs", ["org_id"], ["id"])

    op.drop_table("staff_audit_log")
    op.drop_table("org_invites")
    op.execute("DROP TYPE IF EXISTS org_invite_status")
    op.drop_table("org_members")

    op.drop_column("users", "is_platform_staff")
    op.drop_column("orgs", "max_parallel_tickets")
