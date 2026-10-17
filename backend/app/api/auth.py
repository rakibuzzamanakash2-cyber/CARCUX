"""Login and current-user endpoints."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import AppSettings, CurrentUser, DbSession, client_ip, too_many
from app.core.security import create_access_token, hash_password, needs_rehash, verify_password
from app.schemas.auth import LoginRequest, PasswordChange, TokenResponse
from app.schemas.user import UserRead
from app.services import audit, throttle
from app.services.users import get_by_email

router = APIRouter(prefix="/auth", tags=["auth"])

# One message for every failure, so responses do not reveal which accounts exist.
_INVALID = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: DbSession, settings: AppSettings):
    # Limits apply to every email, existing or not, so a refusal reveals nothing; and
    # before the password is checked, so a locked-out guesser learns nothing either.
    ip, key = client_ip(request), throttle.key_for(settings, body.email)
    try:
        throttle.check(db, throttle.STAFF_LOGIN, key=key, ip=ip)
    except throttle.TooManyAttemptsError as exc:
        user = get_by_email(db, body.email)
        audit.record(
            db,
            audit.AuditAction.LOGIN_THROTTLED,
            actor_id=user.id if user else None,
            ip_address=ip,
            details={"retry_after": exc.retry_after},
        )
        db.commit()
        raise too_many(exc) from None

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
        throttle.record(db, throttle.STAFF_LOGIN, key=key, ip=ip)
        db.commit()
        raise _INVALID

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    user.last_login_at = datetime.now(UTC)
    throttle.clear(db, throttle.STAFF_LOGIN, key=key, ip=ip)
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
    key = throttle.key_for(settings, str(user.id))
    try:
        throttle.check(db, throttle.PASSWORD_CHECK, key=key)
    except throttle.TooManyAttemptsError as exc:
        raise too_many(exc) from None
    if not verify_password(user.password_hash, body.current_password):
        throttle.record(db, throttle.PASSWORD_CHECK, key=key)
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
