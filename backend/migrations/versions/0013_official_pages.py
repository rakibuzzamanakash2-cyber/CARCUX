"""official pages

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-16 13:50:29.645022

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema: verified official pages and the official role."""
    # A new enum value must be committed before a constraint can use it.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'official'")
    op.create_table(
        "official_pages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("name_bn", sa.String(length=200), nullable=True),
        sa.Column(
            "kind",
            sa.Enum(
                "head_of_government",
                "ministry",
                "department",
                "city_corporation",
                "district_administration",
                "member_of_parliament",
                "agency",
                name="official_page_kind",
            ),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("website", sa.String(length=300), nullable=True),
        sa.Column("contact_email", sa.String(length=320), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "verified", "suspended", name="official_page_status"),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "verification_method",
            sa.Enum("official_email", "official_letter", name="verification_method"),
            nullable=True,
        ),
        sa.Column("verification_note", sa.Text(), nullable=True),
        sa.Column("document_key", sa.String(length=300), nullable=True),
        sa.Column("document_type", sa.String(length=50), nullable=True),
        sa.Column("document_sha256", sa.String(length=64), nullable=True),
        sa.Column("verified_by_id", sa.Uuid(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suspended_reason", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name=op.f("fk_official_pages_created_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["verified_by_id"], ["users.id"], name=op.f("fk_official_pages_verified_by_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_official_pages")),
        sa.UniqueConstraint("slug", name=op.f("uq_official_pages_slug")),
    )
    op.add_column("users", sa.Column("official_page_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_users_official_page_id"), "users", ["official_page_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_users_official_page_id_official_pages"),
        "users",
        "official_pages",
        ["official_page_id"],
        ["id"],
    )
    op.create_check_constraint(
        op.f("ck_users_official_has_page"),
        "users",
        "(role = 'official') = (official_page_id IS NOT NULL)",
    )


def downgrade() -> None:
    """Downgrade schema. Official accounts become viewers (the audit log refers to them,
    so they are kept); the 'official' role value stays (PostgreSQL cannot drop it)."""
    op.execute("UPDATE users SET role = 'viewer', official_page_id = NULL WHERE role = 'official'")
    op.drop_constraint(op.f("ck_users_official_has_page"), "users", type_="check")
    op.drop_constraint(
        op.f("fk_users_official_page_id_official_pages"), "users", type_="foreignkey"
    )
    op.drop_index(op.f("ix_users_official_page_id"), table_name="users")
    op.drop_column("users", "official_page_id")
    op.drop_table("official_pages")
    for name in ("official_page_kind", "official_page_status", "verification_method"):
        sa.Enum(name=name).drop(op.get_bind(), checkfirst=True)
