"""statements

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-16 15:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Statements are never edited or deleted; a correction is a new statement.
FUNCTION = """
CREATE FUNCTION statements_are_permanent() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'statements are permanent: publish a correction instead';
END;
$$ LANGUAGE plpgsql;
"""
TRIGGER = """
CREATE TRIGGER statements_are_permanent BEFORE UPDATE OR DELETE ON statements
FOR EACH ROW EXECUTE FUNCTION statements_are_permanent();
"""


def upgrade() -> None:
    """Upgrade schema: official statements, permanent once published."""
    op.create_table(
        "statements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("page_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column(
            "finding",
            sa.Enum(
                "confirmed", "partly_confirmed", "denied", "under_review", name="statement_finding"
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("supersedes_id", sa.Uuid(), nullable=True),
        sa.Column("informed_by_carcux", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("brief", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name=op.f("fk_statements_author_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["event_id"], ["events.id"], name=op.f("fk_statements_event_id_events")
        ),
        sa.ForeignKeyConstraint(
            ["page_id"], ["official_pages.id"], name=op.f("fk_statements_page_id_official_pages")
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"],
            ["statements.id"],
            name=op.f("fk_statements_supersedes_id_statements"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_statements")),
        sa.UniqueConstraint("supersedes_id", name=op.f("uq_statements_supersedes_id")),
    )
    op.create_index(op.f("ix_statements_event_id"), "statements", ["event_id"], unique=False)
    op.create_index(op.f("ix_statements_page_id"), "statements", ["page_id"], unique=False)
    op.execute(FUNCTION)
    op.execute(TRIGGER)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS statements_are_permanent ON statements")
    op.execute("DROP FUNCTION IF EXISTS statements_are_permanent()")
    op.drop_index(op.f("ix_statements_page_id"), table_name="statements")
    op.drop_index(op.f("ix_statements_event_id"), table_name="statements")
    op.drop_table("statements")
    sa.Enum(name="statement_finding").drop(op.get_bind(), checkfirst=True)
