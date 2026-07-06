"""add in_review ticket state (T-102)

Revision ID: a1b2c3d4e5f6
Revises: 0cf581260d39
Create Date: 2026-07-06 08:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "0cf581260d39"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Postgres allows ADD VALUE inside a transaction as long as the new value isn't
    # referenced by another statement in the same transaction (PG 12+) — safe here
    # since this migration only adds the value.
    op.execute("ALTER TYPE ticket_state ADD VALUE IF NOT EXISTS 'in_review'")


def downgrade() -> None:
    # Postgres has no DROP VALUE for enums; removing 'in_review' requires rebuilding
    # the type (create new type, cast column, drop old, rename) and only makes sense
    # if no row is in that state. Left as a no-op — the value simply becomes unused
    # on downgrade, matching the pattern accepted for this repo's other native enums.
    pass
