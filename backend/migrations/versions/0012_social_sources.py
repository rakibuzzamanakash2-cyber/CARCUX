"""social and video platform sources

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-15 21:30:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema: links pasted from social media and video platforms."""
    op.execute("ALTER TYPE source_type ADD VALUE IF NOT EXISTS 'social'")
    op.execute("ALTER TYPE source_type ADD VALUE IF NOT EXISTS 'video_platform'")


def downgrade() -> None:
    """PostgreSQL cannot drop values from an enum type; the two values stay unused."""
