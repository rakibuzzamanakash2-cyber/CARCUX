"""copy decisions

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-15 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "copy_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.Column("origin_evidence_id", sa.Uuid(), nullable=True),
        sa.Column("decided_by_id", sa.Uuid(), nullable=False),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_id"], ["users.id"], name=op.f("fk_copy_decisions_decided_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["event_evidence.id"],
            name=op.f("fk_copy_decisions_evidence_id_event_evidence"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["origin_evidence_id"],
            ["event_evidence.id"],
            name=op.f("fk_copy_decisions_origin_evidence_id_event_evidence"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_copy_decisions")),
        sa.UniqueConstraint("evidence_id", name=op.f("uq_copy_decisions_evidence_id")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("copy_decisions")
