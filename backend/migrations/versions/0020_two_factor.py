"""two-factor sign-in: encrypted authenticator secrets and hashed recovery codes

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-17 16:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0020"
down_revision: str | Sequence[str] | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("users", sa.Column("totp_secret", sa.String(200), nullable=True))
    op.add_column("users", sa.Column("totp_pending", sa.String(200), nullable=True))
    op.add_column("users", sa.Column("totp_enabled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("totp_last_counter", sa.BigInteger(), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "recovery_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    for name in ("recovery_codes", "totp_last_counter", "totp_enabled_at", "totp_pending",
                 "totp_secret"):  # fmt: skip
        op.drop_column("users", name)
