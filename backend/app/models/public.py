"""The public side: people who sign up with an email address to like, comment on and
share official statements. Kept apart from staff accounts (`users`): a public account
can never reach staff endpoints, and its token is of another type.

What is stored about a person: email (never shown), a display name, a password hash,
when they verified the email and signed in. Deleting an account deletes its likes,
comments and reports.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AccountStatus(enum.StrEnum):
    ACTIVE = "active"
    BANNED = "banned"


class PublicAccount(Base):
    __tablename__ = "public_accounts"
    __table_args__ = (CheckConstraint("email = lower(email)", name="email_lowercase"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(50))
    password_hash: Mapped[str] = mapped_column(String(255))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # SHA-256 of the emailed verification token; the token itself is never stored.
    verify_token_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    verify_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[AccountStatus] = mapped_column(
        Enum(AccountStatus, name="public_account_status",
             values_callable=lambda e: [m.value for m in e]),
        default=AccountStatus.ACTIVE, server_default=AccountStatus.ACTIVE.value,
    )  # fmt: skip
    banned_reason: Mapped[str | None] = mapped_column(Text)
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StatementLike(Base):
    __tablename__ = "statement_likes"

    statement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("statements.id"), primary_key=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("public_accounts.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StatementComment(Base):
    __tablename__ = "statement_comments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    statement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("statements.id"), index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("public_accounts.id", ondelete="CASCADE"), index=True
    )
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Hidden by a moderator, or automatically after enough reports (hidden_by is then null).
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hidden_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    hidden_reason: Mapped[str | None] = mapped_column(Text)
    # A moderator looked at the reports and kept it: further reports do not hide it again.
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    account = relationship("PublicAccount", lazy="joined")


class CommentReport(Base):
    __tablename__ = "comment_reports"

    comment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("statement_comments.id", ondelete="CASCADE"), primary_key=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("public_accounts.id", ondelete="CASCADE"), primary_key=True
    )
    reason: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IncidentOpinion(Base):
    """What a member of the public says about an incident (an event an office has posted
    about). Shown at once as an opinion, not verified; also becomes a signal for analysts,
    from a source of its own per account."""

    __tablename__ = "incident_opinions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id"), index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("public_accounts.id", ondelete="CASCADE"), index=True
    )
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hidden_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    hidden_reason: Mapped[str | None] = mapped_column(Text)
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("signals.id", ondelete="SET NULL")
    )

    account = relationship("PublicAccount", lazy="joined")


class OpinionReport(Base):
    __tablename__ = "opinion_reports"

    opinion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incident_opinions.id", ondelete="CASCADE"), primary_key=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("public_accounts.id", ondelete="CASCADE"), primary_key=True
    )
    reason: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
