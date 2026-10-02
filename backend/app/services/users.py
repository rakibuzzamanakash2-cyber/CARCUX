"""Account operations shared by the API and the command line."""

import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import Role, User
from app.services import audit


class EmailAlreadyRegisteredError(Exception):
    pass


# Account emails are login names; CARCUX never sends mail to them. Internal domains
# such as "office.local" are therefore allowed. One rule, used by the API and the CLI.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s.]+$")
MAX_EMAIL_LENGTH = 320


def normalise_email(value: str) -> str:
    """Return the canonical (lowercase) form of an account email, or raise ValueError."""
    email = value.strip().lower()
    if len(email) > MAX_EMAIL_LENGTH or not _EMAIL_RE.fullmatch(email):
        raise ValueError("must look like name@domain.tld")
    return email


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.strip().lower()))


def create_user(
    db: Session,
    *,
    email: str,
    full_name: str,
    password: str,
    role: Role,
    actor_id: uuid.UUID | None,
    action: str = audit.AuditAction.USER_CREATED,
    ip_address: str | None = None,
) -> User:
    email = normalise_email(email)
    if get_by_email(db, email) is not None:
        raise EmailAlreadyRegisteredError(email)

    user = User(
        email=email,
        full_name=full_name.strip(),
        password_hash=hash_password(password),
        role=role,
    )
    db.add(user)
    db.flush()  # assigns user.id for the audit record
    audit.record(
        db,
        action,
        actor_id=actor_id,
        target_type="user",
        target_id=user.id,
        ip_address=ip_address,
        details={"role": role.value},
    )
    return user


def count_admins(db: Session) -> int:
    return db.scalar(
        select(func.count()).select_from(User).where(User.role == Role.ADMIN, User.is_active)
    )
