"""add edit event kind (T-103)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-06 09:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE event_kind ADD VALUE IF NOT EXISTS 'edit'")


def downgrade() -> None:
    # Postgres has no DROP VALUE for enums; see a1b2c3d4e5f6's downgrade for the same
    # accepted no-op pattern used elsewhere in this repo.
    pass
