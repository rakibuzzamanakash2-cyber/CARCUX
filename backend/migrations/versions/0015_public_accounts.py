"""public accounts, likes, comments and reports

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-16 16:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema: the public side (accounts, likes, comments, reports)."""
    op.create_table(
        "public_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=50), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verify_token_hash", sa.String(length=64), nullable=True),
        sa.Column("verify_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum("active", "banned", name="public_account_status"),
            server_default="active",
            nullable=False,
        ),
        sa.Column("banned_reason", sa.Text(), nullable=True),
        sa.Column("token_version", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_public_accounts_email_lowercase")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_public_accounts")),
        sa.UniqueConstraint("email", name=op.f("uq_public_accounts_email")),
    )
    op.create_index(
        op.f("ix_public_accounts_verify_token_hash"),
        "public_accounts",
        ["verify_token_hash"],
        unique=False,
    )
    op.create_table(
        "statement_comments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("statement_id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["public_accounts.id"],
            name=op.f("fk_statement_comments_account_id_public_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["hidden_by_id"], ["users.id"], name=op.f("fk_statement_comments_hidden_by_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["statement_id"],
            ["statements.id"],
            name=op.f("fk_statement_comments_statement_id_statements"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_statement_comments")),
    )
    op.create_index(
        op.f("ix_statement_comments_account_id"), "statement_comments", ["account_id"], unique=False
    )
    op.create_index(
        op.f("ix_statement_comments_statement_id"),
        "statement_comments",
        ["statement_id"],
        unique=False,
    )
    op.create_table(
        "statement_likes",
        sa.Column("statement_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["public_accounts.id"],
            name=op.f("fk_statement_likes_account_id_public_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["statement_id"],
            ["statements.id"],
            name=op.f("fk_statement_likes_statement_id_statements"),
        ),
        sa.PrimaryKeyConstraint("statement_id", "account_id", name=op.f("pk_statement_likes")),
    )
    op.create_index(
        op.f("ix_statement_likes_account_id"), "statement_likes", ["account_id"], unique=False
    )
    op.create_table(
        "comment_reports",
        sa.Column("comment_id", sa.Uuid(), nullable=False),
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
            name=op.f("fk_comment_reports_account_id_public_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["comment_id"],
            ["statement_comments.id"],
            name=op.f("fk_comment_reports_comment_id_statement_comments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("comment_id", "account_id", name=op.f("pk_comment_reports")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("comment_reports")
    op.drop_index(op.f("ix_statement_likes_account_id"), table_name="statement_likes")
    op.drop_table("statement_likes")
    op.drop_index(op.f("ix_statement_comments_statement_id"), table_name="statement_comments")
    op.drop_index(op.f("ix_statement_comments_account_id"), table_name="statement_comments")
    op.drop_table("statement_comments")
    op.drop_index(op.f("ix_public_accounts_verify_token_hash"), table_name="public_accounts")
    op.drop_table("public_accounts")
    sa.Enum(name="public_account_status").drop(op.get_bind(), checkfirst=True)
