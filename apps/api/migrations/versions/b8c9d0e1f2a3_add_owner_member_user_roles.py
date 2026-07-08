"""add owner/member user_role enum values (T-201)

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-07-08 10:00:00.000000

Split into its own migration (rather than combined with the org_members/org_invites
work in the next revision) because Postgres will not let a transaction USE an enum
value it just ADDed in the same transaction — every other migration's `upgrade()`
runs as one transaction, so the new values must land and commit here first.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8c9d0e1f2a3"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'owner'")
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'member'")


def downgrade() -> None:
    # Postgres has no DROP VALUE for enums; see a1b2c3d4e5f6's downgrade for the same
    # accepted no-op pattern used elsewhere in this repo.
    pass
