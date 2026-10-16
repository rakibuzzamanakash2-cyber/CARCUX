"""Account management. Admin only."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select

from app.api.deps import DbSession, client_ip, require_roles
from app.core.security import hash_password
from app.models.official import OfficialPage
from app.models.user import Role, User
from app.schemas.auth import PasswordReset
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
            official_page_id=_page_or_422(db, body.official_page_id),
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
    role = changes.get("role", user.role)
    if role == Role.OFFICIAL:
        page_id = _page_or_422(db, changes.get("official_page_id", user.official_page_id))
        if page_id is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "An official account needs its official page"
            )
        if page_id != user.official_page_id:
            changes["official_page_id"] = page_id
    else:
        if body.official_page_id is not None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Only official accounts belong to an official page",
            )
        if user.official_page_id is not None:
            changes["official_page_id"] = None  # leaving the official role

    removes_admin = user.role == Role.ADMIN and (
        changes.get("role", Role.ADMIN) != Role.ADMIN or changes.get("is_active") is False
    )
    if removes_admin and user.is_active and count_admins(db) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot remove the last active admin")

    before = {k: getattr(user, k) for k in changes}
    for field, value in changes.items():
        setattr(user, field, value)

    # Role or access changes take effect immediately: revoke existing tokens.
    if {"role", "is_active", "official_page_id"} & changes.keys():
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
    db.refresh(user)
    return user


def _plain(value):
    if isinstance(value, Role):
        return value.value
    return str(value) if isinstance(value, uuid.UUID) else value


def _page_or_422(db, page_id: uuid.UUID | None) -> uuid.UUID | None:
    if page_id is None:
        return None
    if db.get(OfficialPage, page_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown official page")
    return page_id


@router.post("/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    user_id: uuid.UUID, body: PasswordReset, request: Request, db: DbSession, admin: AdminUser
):
    """Set a temporary password for someone who forgot theirs. Signs them out everywhere."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1
    audit.record(
        db,
        audit.AuditAction.PASSWORD_RESET,
        actor_id=admin.id,
        target_type="user",
        target_id=user.id,
        ip_address=client_ip(request),
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
