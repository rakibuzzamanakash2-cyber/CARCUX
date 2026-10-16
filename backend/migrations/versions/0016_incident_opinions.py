"""incident opinions and their reports

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-16 20:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema: people's opinions on incidents, and reports on them."""
    op.create_table(
        "incident_opinions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hidden_by_id", sa.Uuid(), nullable=True),
        sa.Column("hidden_reason", sa.Text(), nullable=True),
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("signal_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["public_accounts.id"],
            name=op.f("fk_incident_opinions_account_id_public_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"], ["events.id"], name=op.f("fk_incident_opinions_event_id_events")
        ),
        sa.ForeignKeyConstraint(
            ["hidden_by_id"], ["users.id"], name=op.f("fk_incident_opinions_hidden_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["signal_id"],
            ["signals.id"],
            name=op.f("fk_incident_opinions_signal_id_signals"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incident_opinions")),
    )
    op.create_index(
        op.f("ix_incident_opinions_account_id"), "incident_opinions", ["account_id"], unique=False
    )
    op.create_index(
        op.f("ix_incident_opinions_event_id"), "incident_opinions", ["event_id"], unique=False
    )
    op.create_table(
        "opinion_reports",
        sa.Column("opinion_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(length=40), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["public_accounts.id"],
            name=op.f("fk_opinion_reports_account_id_public_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["opinion_id"],
            ["incident_opinions.id"],
            name=op.f("fk_opinion_reports_opinion_id_incident_opinions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("opinion_id", "account_id", name=op.f("pk_opinion_reports")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("opinion_reports")
    op.drop_index(op.f("ix_incident_opinions_event_id"), table_name="incident_opinions")
    op.drop_index(op.f("ix_incident_opinions_account_id"), table_name="incident_opinions")
    op.drop_table("incident_opinions")
