"""Staff, field-worker and official accounts.

Users are authorized operators of CARCUX, and officials who publish statements for a
verified official page. This table holds only what is needed to authenticate and
authorize them.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Role(enum.StrEnum):
    ADMIN = "admin"  # manages accounts and system settings
    ANALYST = "analyst"  # reviews events, verifies assessments
    FIELD_WORKER = "field_worker"  # submits field reports
    VIEWER = "viewer"  # read-only access to the dashboard
    OFFICIAL = "official"  # publishes statements for one verified official page


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint(
            "(role = 'official') = (official_page_id IS NOT NULL)", name="official_has_page"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="user_role", values_callable=lambda r: [m.value for m in r])
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    # Officials only: the page they speak for.
    official_page_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("official_pages.id", use_alter=True), index=True
    )
    official_page = relationship(
        "OfficialPage", foreign_keys=[official_page_id], back_populates="members", lazy="joined"
    )

    # Incremented to revoke every token issued so far (deactivation, role change,
    # password change). Tokens carry the version they were issued with.
    token_version: Mapped[int] = mapped_column(default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
