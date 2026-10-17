"""Login (with optional two-factor), current user, password and two-factor settings."""

import time
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import AppSettings, CurrentUser, DbSession, client_ip, limit, too_many
from app.core import totp
from app.core.config import Settings
from app.core.security import (
    InvalidTokenError,
    create_access_token,
    create_challenge_token,
    decode_challenge_token,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LoginResult,
    PasswordChange,
    RecoveryCodes,
    TokenResponse,
    TwoFactorCode,
    TwoFactorDisable,
    TwoFactorLogin,
    TwoFactorSetup,
    TwoFactorStatus,
)
from app.schemas.user import MeRead
from app.services import audit, throttle
from app.services.users import get_by_email

router = APIRouter(prefix="/auth", tags=["auth"])

# One message for every failure, so responses do not reveal which accounts exist.
_INVALID = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
)


@router.post("/login", response_model=LoginResult)
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
    throttle.clear(db, throttle.STAFF_LOGIN, key=key, ip=ip)
    if user.two_factor_enabled:
        # The password was right; the code comes next (POST /auth/login/two-factor).
        db.commit()
        challenge = create_challenge_token(settings, user.id, user.token_version)
        return LoginResult(two_factor_required=True, challenge=challenge, expires_in=300)
    return _signed_in(db, settings, user, request, None)


def _signed_in(db, settings: Settings, user: User, request: Request, second: str | None):
    user.last_login_at = datetime.now(UTC)
    audit.record(
        db, audit.AuditAction.LOGIN_SUCCEEDED, actor_id=user.id, ip_address=client_ip(request),
        details={"two_factor": second} if second else None,
    )  # fmt: skip
    db.commit()
    token, expires_in = create_access_token(settings, user.id, user.role.value, user.token_version)
    return LoginResult(access_token=token, expires_in=expires_in)


def _check_code(settings: Settings, user: User, code: str) -> str | None:
    """ "app" for a current authenticator code, "recovery" for an unused recovery code
    (then used up), or None."""
    if user.totp_secret:
        counter = totp.verify(
            totp.decrypt(settings, user.totp_secret), code, time.time(), user.totp_last_counter
        )
        if counter is not None:
            user.totp_last_counter = counter
            return "app"
    digest = totp.recovery_hash(settings, code)
    if digest in (user.recovery_codes or []):
        user.recovery_codes = [h for h in user.recovery_codes if h != digest]
        return "recovery"
    return None


def _code_or_fail(db, settings: Settings, user: User, code: str, request: Request) -> str:
    key = throttle.key_for(settings, f"2fa:{user.id}")
    limit(db, throttle.TWO_FACTOR, key=key, count=False)
    kind = _check_code(settings, user, code)
    if kind is None:
        throttle.record(db, throttle.TWO_FACTOR, key=key)
        audit.record(
            db, audit.AuditAction.TWO_FACTOR_FAILED, actor_id=user.id,
            ip_address=client_ip(request),
        )  # fmt: skip
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "That code is not right. Try again.")
    if kind == "recovery":
        audit.record(
            db, audit.AuditAction.TWO_FACTOR_RECOVERY_USED, actor_id=user.id,
            ip_address=client_ip(request), details={"left": len(user.recovery_codes)},
        )  # fmt: skip
    return kind


@router.post("/login/two-factor", response_model=LoginResult)
def login_two_factor(body: TwoFactorLogin, request: Request, db: DbSession, settings: AppSettings):
    """The second step: the challenge from /auth/login and a code from the
    authenticator app (or a recovery code)."""
    try:
        user_id, version = decode_challenge_token(settings, body.challenge)
    except InvalidTokenError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "This sign-in has expired. Enter your password again."
        ) from None
    user = db.get(User, user_id)
    if user is None or not user.is_active or user.token_version != version:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in again.")
    if not user.two_factor_enabled:
        return _signed_in(db, settings, user, request, None)
    kind = _code_or_fail(db, settings, user, body.code, request)
    return _signed_in(db, settings, user, request, kind)


@router.get("/me", response_model=MeRead)
def me(user: CurrentUser, settings: AppSettings):
    out = MeRead.model_validate(user)
    out.two_factor_setup_needed = _setup_needed(settings, user)
    return out


def _setup_needed(settings: Settings, user: User) -> bool:
    return user.role.value in settings.two_factor_roles and not user.two_factor_enabled


# --- Two-factor settings (your own account) ------------------------------------------------


@router.get("/two-factor", response_model=TwoFactorStatus)
def two_factor_status(user: CurrentUser, settings: AppSettings):
    return TwoFactorStatus(
        enabled=user.two_factor_enabled,
        enabled_at=user.totp_enabled_at,
        recovery_codes_left=len(user.recovery_codes or []),
        required=user.role.value in settings.two_factor_roles,
    )


@router.post("/two-factor/setup", response_model=TwoFactorSetup)
def two_factor_setup(db: DbSession, settings: AppSettings, user: CurrentUser):
    """A new secret to add to an authenticator app; it takes effect once a code from it
    is confirmed (POST /auth/two-factor/enable)."""
    if user.two_factor_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Two-factor sign-in is already on.")
    secret = totp.new_secret()
    user.totp_pending = totp.encrypt(settings, secret)
    db.commit()
    uri = totp.otpauth_uri(secret, user.email)
    return TwoFactorSetup(secret=secret, otpauth_uri=uri, qr_svg=totp.qr_svg(uri))


@router.post("/two-factor/enable", response_model=RecoveryCodes)
def two_factor_enable(
    body: TwoFactorCode, request: Request, db: DbSession, settings: AppSettings, user: CurrentUser
):
    """Confirm the app works with one of its codes. Returns recovery codes, shown once."""
    if user.two_factor_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Two-factor sign-in is already on.")
    if not user.totp_pending:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Start the set-up first.")
    key = throttle.key_for(settings, f"2fa:{user.id}")
    limit(db, throttle.TWO_FACTOR, key=key, count=False)
    secret = totp.decrypt(settings, user.totp_pending)
    counter = totp.verify(secret, body.code, time.time(), None)
    if counter is None:
        throttle.record(db, throttle.TWO_FACTOR, key=key)
        db.commit()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "That code is not right. Check the phone's clock and enter the newest code.",
        )
    codes = totp.recovery_codes()
    user.totp_secret, user.totp_pending = user.totp_pending, None
    user.totp_enabled_at = datetime.now(UTC)
    user.totp_last_counter = counter
    user.recovery_codes = [totp.recovery_hash(settings, c) for c in codes]
    audit.record(
        db, audit.AuditAction.TWO_FACTOR_ENABLED, actor_id=user.id, target_type="user",
        target_id=user.id, ip_address=client_ip(request),
    )  # fmt: skip
    db.commit()
    return RecoveryCodes(recovery_codes=codes)


@router.post("/two-factor/recovery-codes", response_model=RecoveryCodes)
def two_factor_new_codes(
    body: TwoFactorCode, request: Request, db: DbSession, settings: AppSettings, user: CurrentUser
):
    """Replace the recovery codes (the old ones stop working). Needs a current code."""
    if not user.two_factor_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Two-factor sign-in is off.")
    _code_or_fail(db, settings, user, body.code, request)
    codes = totp.recovery_codes()
    user.recovery_codes = [totp.recovery_hash(settings, c) for c in codes]
    db.commit()
    return RecoveryCodes(recovery_codes=codes)


@router.post("/two-factor/disable", status_code=status.HTTP_204_NO_CONTENT)
def two_factor_disable(
    body: TwoFactorDisable,
    request: Request,
    db: DbSession,
    settings: AppSettings,
    user: CurrentUser,
):
    if user.role.value in settings.two_factor_roles:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Your role must use two-factor sign-in. If you lost your phone, ask an admin "
            "to reset it.",
        )
    if not user.two_factor_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Two-factor sign-in is off.")
    key = throttle.key_for(settings, str(user.id))
    limit(db, throttle.PASSWORD_CHECK, key=key, count=False)
    if not verify_password(user.password_hash, body.password):
        throttle.record(db, throttle.PASSWORD_CHECK, key=key)
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    _code_or_fail(db, settings, user, body.code, request)
    clear_two_factor(user)
    audit.record(
        db, audit.AuditAction.TWO_FACTOR_DISABLED, actor_id=user.id, target_type="user",
        target_id=user.id, ip_address=client_ip(request),
    )  # fmt: skip
    db.commit()


def clear_two_factor(user: User) -> None:
    user.totp_secret = user.totp_pending = None
    user.totp_enabled_at = None
    user.totp_last_counter = None
    user.recovery_codes = []


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
