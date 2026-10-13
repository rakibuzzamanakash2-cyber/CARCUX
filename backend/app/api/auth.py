"""Login and current-user endpoints."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import AppSettings, CurrentUser, DbSession, client_ip
from app.core.security import create_access_token, hash_password, needs_rehash, verify_password
from app.schemas.auth import LoginRequest, PasswordChange, TokenResponse
from app.schemas.user import UserRead
from app.services import audit
from app.services.users import get_by_email

router = APIRouter(prefix="/auth", tags=["auth"])

# One message for every failure, so responses do not reveal which accounts exist.
_INVALID = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: DbSession, settings: AppSettings):
    user = get_by_email(db, body.email)
    password_ok = verify_password(user.password_hash if user else None, body.password)

    if user is None or not password_ok or not user.is_active:
        reason = (
            "unknown_email"
            if user is None
            else ("wrong_password" if not password_ok else "inactive_account")
        )
        audit.record(
            db,
            audit.AuditAction.LOGIN_FAILED,
            actor_id=user.id if user else None,
            ip_address=client_ip(request),
            details={"reason": reason},
        )
        db.commit()
        raise _INVALID

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    user.last_login_at = datetime.now(UTC)
    audit.record(
        db, audit.AuditAction.LOGIN_SUCCEEDED, actor_id=user.id, ip_address=client_ip(request)
    )
    db.commit()

    token, expires_in = create_access_token(settings, user.id, user.role.value, user.token_version)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=UserRead)
def me(user: CurrentUser):
    return user


@router.post("/password", response_model=TokenResponse)
def change_password(
    body: PasswordChange,
    request: Request,
    db: DbSession,
    settings: AppSettings,
    user: CurrentUser,
):
    """Change your own password. Signs out every other session; returns a fresh token."""
    if not verify_password(user.password_hash, body.current_password):
        audit.record(
            db,
            audit.AuditAction.PASSWORD_CHANGE_FAILED,
            actor_id=user.id,
            target_type="user",
            target_id=user.id,
            ip_address=client_ip(request),
        )
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    if body.new_password == body.current_password:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Choose a password different from the current one",
        )
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1
    audit.record(
        db,
        audit.AuditAction.PASSWORD_CHANGED,
        actor_id=user.id,
        target_type="user",
        target_id=user.id,
        ip_address=client_ip(request),
    )
    db.commit()
    token, expires_in = create_access_token(settings, user.id, user.role.value, user.token_version)
    return TokenResponse(access_token=token, expires_in=expires_in)
