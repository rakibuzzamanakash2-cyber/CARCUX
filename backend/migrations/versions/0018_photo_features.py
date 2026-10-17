"""photo features from ai/media: perceptual and mirrored hashes, text in photos

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-17 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema: hashes and OCR columns on field report photos."""
    for name in ("phash", "dhash_mirrored", "phash_mirrored"):
        op.add_column("field_report_media", sa.Column(name, sa.String(16), nullable=True))
    op.add_column("field_report_media", sa.Column("ocr_text", sa.Text(), nullable=True))
    op.add_column("field_report_media", sa.Column("ocr_confidence", sa.Float(), nullable=True))
    op.add_column("field_report_media", sa.Column("ocr_status", sa.String(10), nullable=True))
    op.create_index(
        op.f("ix_field_report_media_ocr_status"), "field_report_media", ["ocr_status"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_field_report_media_ocr_status"), table_name="field_report_media")
    for name in (
        "ocr_status", "ocr_confidence", "ocr_text", "phash_mirrored", "dhash_mirrored", "phash",
    ):  # fmt: skip
        op.drop_column("field_report_media", name)
