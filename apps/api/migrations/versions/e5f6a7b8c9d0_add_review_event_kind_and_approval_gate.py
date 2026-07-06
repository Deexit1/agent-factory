"""add review event kind and approval gate (T-106)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-06 13:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE event_kind ADD VALUE IF NOT EXISTS 'review'")
    op.execute("ALTER TYPE approval_gate ADD VALUE IF NOT EXISTS 'review'")


def downgrade() -> None:
    # Postgres has no DROP VALUE for enums; see a1b2c3d4e5f6's downgrade for the same
    # accepted no-op pattern used elsewhere in this repo.
    pass
