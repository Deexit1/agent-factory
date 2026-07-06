"""add assignment event kind (T-104)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-06 10:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE event_kind ADD VALUE IF NOT EXISTS 'assignment'")


def downgrade() -> None:
    # Postgres has no DROP VALUE for enums; see a1b2c3d4e5f6's downgrade for the same
    # accepted no-op pattern used elsewhere in this repo.
    pass
