"""Account operations shared by the API and the command line."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import Role, User
from app.services import audit


class EmailAlreadyRegisteredError(Exception):
    pass


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
    email = email.strip().lower()
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
