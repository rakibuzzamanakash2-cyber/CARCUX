"""evidence requests: asking field workers to check an event

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-17 18:01:50.164533

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0021"
down_revision: str | Sequence[str] | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "evidence_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("open", "answered", "cancelled", name="evidence_request_status"),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("closed_by_id", sa.Uuid(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("close_note", sa.String(length=300), nullable=True),
        sa.ForeignKeyConstraint(
            ["closed_by_id"], ["users.id"], name=op.f("fk_evidence_requests_closed_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name=op.f("fk_evidence_requests_created_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["event_id"], ["events.id"], name=op.f("fk_evidence_requests_event_id_events")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence_requests")),
    )
    op.create_index(
        op.f("ix_evidence_requests_event_id"), "evidence_requests", ["event_id"], unique=False
    )
    op.create_index(
        op.f("ix_evidence_requests_status"), "evidence_requests", ["status"], unique=False
    )
    op.create_index(
        "one_open_request_per_event",
        "evidence_requests",
        ["event_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )
    op.add_column("field_reports", sa.Column("request_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_field_reports_request_id"), "field_reports", ["request_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_field_reports_request_id_evidence_requests"),
        "field_reports",
        "evidence_requests",
        ["request_id"],
        ["id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        op.f("fk_field_reports_request_id_evidence_requests"), "field_reports", type_="foreignkey"
    )
    op.drop_index(op.f("ix_field_reports_request_id"), table_name="field_reports")
    op.drop_column("field_reports", "request_id")
    op.drop_index(
        "one_open_request_per_event",
        table_name="evidence_requests",
        postgresql_where=sa.text("status = 'open'"),
    )
    op.drop_index(op.f("ix_evidence_requests_status"), table_name="evidence_requests")
    op.drop_index(op.f("ix_evidence_requests_event_id"), table_name="evidence_requests")
    op.drop_table("evidence_requests")
    sa.Enum(name="evidence_request_status").drop(op.get_bind(), checkfirst=True)
