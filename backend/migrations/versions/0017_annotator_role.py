"""annotator role: second annotators who can only use the blind queue

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-16 23:50:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema: the annotator role."""
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'annotator'")


def downgrade() -> None:
    """Downgrade schema. Annotators become viewers; the 'annotator' value stays
    (PostgreSQL cannot drop an enum value)."""
    op.execute("UPDATE users SET role = 'viewer' WHERE role = 'annotator'")
