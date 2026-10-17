"""throttle events: counted attempts for rate limits on sign-in, sign-up and submissions

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-17 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0019"
down_revision: str | Sequence[str] | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "throttle_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("key", sa.String(64), nullable=True),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_throttle_events")),
    )
    op.create_index("ix_throttle_events_kind_at", "throttle_events", ["kind", "at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_throttle_events_kind_at", table_name="throttle_events")
    op.drop_table("throttle_events")
