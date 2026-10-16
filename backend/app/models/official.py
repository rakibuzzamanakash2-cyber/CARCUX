"""Official pages: verified accounts of government bodies and office holders (the
Prime Minister's Office, a ministry, a city corporation, a district administration,
a member of parliament) that publish statements about events.

Only an admin creates and verifies a page, after confirming it through the office's
own email address or an official letter. How it was verified, by whom and when is kept
on the page and in the audit log. A suspended page is hidden and cannot publish.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _values(e: type[enum.Enum]) -> list[str]:
    return [m.value for m in e]


class PageKind(enum.StrEnum):
    HEAD_OF_GOVERNMENT = "head_of_government"  # Prime Minister's Office, Chief Adviser
    MINISTRY = "ministry"
    DEPARTMENT = "department"  # divisions, directorates (e.g. Fire Service, DDM)
    CITY_CORPORATION = "city_corporation"
    DISTRICT_ADMINISTRATION = "district_administration"
    MEMBER_OF_PARLIAMENT = "member_of_parliament"
    AGENCY = "agency"  # other public bodies (BMD, FFWC, BWDB)


class PageStatus(enum.StrEnum):
    PENDING = "pending"  # created, not yet verified: invisible, cannot publish
    VERIFIED = "verified"
    SUSPENDED = "suspended"  # hidden, cannot publish; can be reinstated


class VerificationMethod(enum.StrEnum):
    OFFICIAL_EMAIL = "official_email"  # confirmed by correspondence with the office's address
    OFFICIAL_LETTER = "official_letter"  # a signed letter on letterhead, scan kept


class OfficialPage(Base):
    __tablename__ = "official_pages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    name_bn: Mapped[str | None] = mapped_column(String(200))
    kind: Mapped[PageKind] = mapped_column(
        Enum(PageKind, name="official_page_kind", values_callable=_values)
    )
    description: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(String(300))
    contact_email: Mapped[str | None] = mapped_column(String(320))

    status: Mapped[PageStatus] = mapped_column(
        Enum(PageStatus, name="official_page_status", values_callable=_values),
        default=PageStatus.PENDING,
        server_default=PageStatus.PENDING.value,
    )
    verification_method: Mapped[VerificationMethod | None] = mapped_column(
        Enum(VerificationMethod, name="verification_method", values_callable=_values)
    )
    verification_note: Mapped[str | None] = mapped_column(Text)
    # The letter or email printout, stored under the media directory (admins only).
    document_key: Mapped[str | None] = mapped_column(String(300))
    document_type: Mapped[str | None] = mapped_column(String(50))
    document_sha256: Mapped[str | None] = mapped_column(String(64))
    verified_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspended_reason: Mapped[str | None] = mapped_column(Text)

    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    verified_by = relationship("User", foreign_keys=[verified_by_id], lazy="joined")
    members = relationship(
        "User", foreign_keys="User.official_page_id", back_populates="official_page"
    )
