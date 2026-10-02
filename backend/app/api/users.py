"""Account management. Admin only."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import DbSession, client_ip, require_roles
from app.models.user import Role, User
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.services import audit
from app.services.users import EmailAlreadyRegisteredError, count_admins, create_user

router = APIRouter(prefix="/users", tags=["users"])

AdminUser = Annotated[User, Depends(require_roles(Role.ADMIN))]


@router.get("", response_model=list[UserRead])
def list_users(db: DbSession, _admin: AdminUser):
    return db.scalars(select(User).order_by(User.created_at)).all()


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create(body: UserCreate, request: Request, db: DbSession, admin: AdminUser):
    try:
        user = create_user(
            db,
            email=body.email,
            full_name=body.full_name,
            password=body.password,
            role=body.role,
            actor_id=admin.id,
            ip_address=client_ip(request),
        )
    except EmailAlreadyRegisteredError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from None
    db.commit()
    return user


@router.patch("/{user_id}", response_model=UserRead)
def update(user_id: uuid.UUID, body: UserUpdate, request: Request, db: DbSession, admin: AdminUser):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    removes_admin = user.role == Role.ADMIN and (
        changes.get("role", Role.ADMIN) != Role.ADMIN or changes.get("is_active") is False
    )
    if removes_admin and user.is_active and count_admins(db) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot remove the last active admin")

    before = {k: getattr(user, k) for k in changes}
    for field, value in changes.items():
        setattr(user, field, value)

    # Role or access changes take effect immediately: revoke existing tokens.
    if "role" in changes or "is_active" in changes:
        user.token_version += 1

    audit.record(
        db,
        audit.AuditAction.USER_UPDATED,
        actor_id=admin.id,
        target_type="user",
        target_id=user.id,
        ip_address=client_ip(request),
        details={
            "changes": {k: {"from": _plain(before[k]), "to": _plain(v)} for k, v in changes.items()}
        },
    )
    db.commit()
    return user


def _plain(value):
    return value.value if isinstance(value, Role) else value
