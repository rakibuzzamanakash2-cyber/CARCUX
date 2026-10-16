"""The public side: accounts, likes, comments, reports and their moderation.

Rules:
- an account must verify its email before it can sign in; banned accounts cannot;
- at most COMMENTS_PER_WINDOW comments per COMMENT_WINDOW per account;
- a comment reported by AUTO_HIDE_REPORTS different people is hidden at once, until a
  moderator restores it (it then stays up whatever further reports say);
- moderators: admins (every comment), and officials (comments on their page's posts);
- banning an account signs it out and hides its comments.
"""

import hashlib
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import hash_password, verify_password
from app.models.official import PageStatus
from app.models.public import (
    AccountStatus,
    CommentReport,
    PublicAccount,
    StatementComment,
    StatementLike,
)
from app.models.statement import Statement
from app.models.user import Role, User
from app.services import audit, mailer
from app.services.users import normalise_email

COMMENTS_PER_WINDOW = 5
COMMENT_WINDOW = timedelta(minutes=10)
AUTO_HIDE_REPORTS = 3
VERIFY_VALID = timedelta(hours=48)
RESEND_AFTER = timedelta(minutes=2)
REPORT_REASONS = ("false_information", "abuse", "spam", "personal_information", "other")
_NAME = re.compile(r"^[\w .'\-ঀ-৿]{2,50}$")


class PublicError(ValueError):
    """A rule was not met; the message says which (shown to the person)."""


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


# --- Accounts -----------------------------------------------------------------------------


def by_email(db: Session, email: str) -> PublicAccount | None:
    return db.scalar(select(PublicAccount).where(PublicAccount.email == email.strip().lower()))


def _send_verification(db: Session, settings: Settings, account: PublicAccount) -> None:
    token = secrets.token_urlsafe(32)
    account.verify_token_hash, account.verify_sent_at = _hash(token), _now()
    link = f"{settings.public_base_url.rstrip('/')}/public/verify?token={token}"
    mailer.send(
        settings, account.email, "Confirm your CARCUX account",
        f"Hello {account.display_name},\n\nConfirm your email address to like and comment on "
        f"official posts on CARCUX:\n\n{link}\n\nThe link works for 48 hours. If you did not "
        "sign up, ignore this email.\n",
    )  # fmt: skip


def signup(db: Session, settings: Settings, *, email: str, display_name: str, password: str):
    """Always looks the same from outside, so it does not reveal which emails exist."""
    email = normalise_email(email)
    name = " ".join(display_name.split())
    if not _NAME.fullmatch(name):
        raise PublicError("Use 2 to 50 letters, digits, spaces, dots or dashes for your name")
    existing = by_email(db, email)
    if existing is not None:
        if existing.email_verified_at is None and existing.status == AccountStatus.ACTIVE:
            if not existing.verify_sent_at or _now() - existing.verify_sent_at > RESEND_AFTER:
                _send_verification(db, settings, existing)
        return
    account = PublicAccount(email=email, display_name=name, password_hash=hash_password(password))
    db.add(account)
    db.flush()
    _send_verification(db, settings, account)


def verify_email(db: Session, token: str) -> PublicAccount:
    account = db.scalar(
        select(PublicAccount).where(PublicAccount.verify_token_hash == _hash(token))
    )
    if (
        account is None
        or account.verify_sent_at is None
        or _now() - account.verify_sent_at > VERIFY_VALID
    ):
        raise PublicError("This link is not valid any more. Sign up again to get a new one.")
    account.email_verified_at, account.verify_token_hash = _now(), None
    return account


def authenticate(db: Session, email: str, password: str) -> PublicAccount:
    account = by_email(db, email)
    ok = verify_password(account.password_hash if account else None, password)
    if account is None or not ok:
        raise PublicError("Wrong email or password")
    if account.email_verified_at is None:
        raise PublicError("Confirm your email first: open the link we sent you")
    if account.status == AccountStatus.BANNED:
        raise PublicError("This account was banned for breaking the rules")
    account.last_login_at = _now()
    return account


def delete_account(db: Session, account: PublicAccount, password: str) -> None:
    if not verify_password(account.password_hash, password):
        raise PublicError("Wrong password")
    db.delete(account)  # likes, comments and reports go with it


# --- Reading ------------------------------------------------------------------------------


def visible_statement(db: Session, statement_id: uuid.UUID) -> Statement | None:
    st = db.get(Statement, statement_id)
    return st if st is not None and st.page.status == PageStatus.VERIFIED else None


def counts(db: Session, ids: list[uuid.UUID]) -> tuple[dict, dict]:
    """Likes and visible comments per statement."""
    if not ids:
        return {}, {}
    likes = dict(
        db.execute(
            select(StatementLike.statement_id, func.count())
            .where(StatementLike.statement_id.in_(ids))
            .group_by(StatementLike.statement_id)
        ).all()
    )
    comments = dict(
        db.execute(
            select(StatementComment.statement_id, func.count())
            .where(StatementComment.statement_id.in_(ids), StatementComment.hidden_at.is_(None))
            .group_by(StatementComment.statement_id)
        ).all()
    )
    return likes, comments


def liked(db: Session, account: PublicAccount | None, ids: list[uuid.UUID]) -> set:
    if account is None or not ids:
        return set()
    return set(
        db.scalars(
            select(StatementLike.statement_id).where(
                StatementLike.account_id == account.id, StatementLike.statement_id.in_(ids)
            )
        )
    )


# --- Taking part --------------------------------------------------------------------------


def set_like(db: Session, account: PublicAccount, statement: Statement, on: bool) -> None:
    existing = db.get(StatementLike, (statement.id, account.id))
    if on and existing is None:
        db.add(StatementLike(statement_id=statement.id, account_id=account.id))
    elif not on and existing is not None:
        db.delete(existing)


def comment(db: Session, account: PublicAccount, statement: Statement, body: str):
    text = body.strip()
    if not 2 <= len(text) <= 1000:
        raise PublicError("A comment is 2 to 1000 characters")
    recent = db.scalar(
        select(func.count()).select_from(StatementComment).where(
            StatementComment.account_id == account.id,
            StatementComment.created_at > _now() - COMMENT_WINDOW,
        )
    )  # fmt: skip
    if recent >= COMMENTS_PER_WINDOW:
        raise PublicError("You are commenting too fast. Try again in a few minutes.")
    c = StatementComment(statement_id=statement.id, account_id=account.id, body=text)
    db.add(c)
    db.flush()
    return c


def report(db: Session, account: PublicAccount, c: StatementComment, reason: str) -> None:
    if reason not in REPORT_REASONS:
        raise PublicError("Choose a reason")
    if c.account_id == account.id:
        raise PublicError("You cannot report your own comment")
    if db.get(CommentReport, (c.id, account.id)) is None:
        db.add(CommentReport(comment_id=c.id, account_id=account.id, reason=reason))
        db.flush()
    reports = db.scalar(
        select(func.count()).select_from(CommentReport).where(CommentReport.comment_id == c.id)
    )
    if reports >= AUTO_HIDE_REPORTS and c.hidden_at is None and c.cleared_at is None:
        c.hidden_at, c.hidden_reason = _now(), "Hidden after reports, waiting for a moderator"


# --- Moderation ---------------------------------------------------------------------------


def can_moderate(user: User, c: StatementComment, db: Session) -> bool:
    if user.role == Role.ADMIN:
        return True
    st = db.get(Statement, c.statement_id)
    return user.role == Role.OFFICIAL and st is not None and user.official_page_id == st.page_id


def hide(db, c: StatementComment, moderator: User, reason: str, ip: str | None) -> None:
    c.hidden_at, c.hidden_by_id, c.hidden_reason = _now(), moderator.id, reason.strip()
    audit.record(
        db, audit.AuditAction.COMMENT_HIDDEN, actor_id=moderator.id, target_type="comment",
        target_id=c.id, ip_address=ip, details={"reason": c.hidden_reason,
                                                "statement_id": str(c.statement_id)},
    )  # fmt: skip


def restore(db, c: StatementComment, moderator: User, ip: str | None) -> None:
    c.hidden_at, c.hidden_by_id, c.hidden_reason, c.cleared_at = None, None, None, _now()
    audit.record(
        db, audit.AuditAction.COMMENT_RESTORED, actor_id=moderator.id, target_type="comment",
        target_id=c.id, ip_address=ip, details={"statement_id": str(c.statement_id)},
    )  # fmt: skip


def ban(db, account: PublicAccount, admin: User, reason: str, ip: str | None) -> None:
    account.status, account.banned_reason = AccountStatus.BANNED, reason.strip()
    account.token_version += 1
    for c in db.scalars(
        select(StatementComment).where(
            StatementComment.account_id == account.id, StatementComment.hidden_at.is_(None)
        )
    ):
        c.hidden_at, c.hidden_by_id, c.hidden_reason = _now(), admin.id, "Account banned"
    audit.record(
        db, audit.AuditAction.PUBLIC_ACCOUNT_BANNED, actor_id=admin.id,
        target_type="public_account", target_id=account.id, ip_address=ip,
        details={"reason": account.banned_reason, "display_name": account.display_name},
    )  # fmt: skip


def unban(db, account: PublicAccount, admin: User, ip: str | None) -> None:
    account.status, account.banned_reason = AccountStatus.ACTIVE, None
    audit.record(
        db, audit.AuditAction.PUBLIC_ACCOUNT_UNBANNED, actor_id=admin.id,
        target_type="public_account", target_id=account.id, ip_address=ip,
    )  # fmt: skip
