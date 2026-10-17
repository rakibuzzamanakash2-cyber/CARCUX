"""Shared request dependencies: database session, current user, role checks."""

import ipaddress
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, app_settings
from app.core.security import InvalidTokenError, decode_access_token
from app.db.session import get_db
from app.models.user import Role, User
from app.services import throttle
from app.services.throttle import TooManyAttemptsError

_bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(app_settings)]

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


# Second annotators must not see anyone else's label, CARCUX's suggestions, the
# agreement figures or the events' evidence. Their accounts reach these routes only;
# every other route that needs a signed-in user refuses them (deny by default).
ANNOTATOR_ROUTES = frozenset(
    {
        ("GET", "/auth/me"),
        ("POST", "/auth/password"),
        ("GET", "/annotation/queue"),
        ("POST", "/annotation/judgements"),
    }
)


# Someone whose role must use two-factor sign-in (Settings.two_factor_roles) and who has
# not set it up yet reaches only these: enough to set it up, and nothing else.
TWO_FACTOR_SETUP_ROUTES = frozenset(
    {
        ("GET", "/auth/me"),
        ("POST", "/auth/password"),
        ("GET", "/auth/two-factor"),
        ("POST", "/auth/two-factor/setup"),
        ("POST", "/auth/two-factor/enable"),
    }
)


def get_current_user(
    request: Request,
    db: DbSession,
    settings: AppSettings,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None:
        raise _UNAUTHORIZED
    try:
        claims = decode_access_token(settings, credentials.credentials)
    except InvalidTokenError:
        raise _UNAUTHORIZED from None

    user = db.get(User, claims.user_id)
    # Reject tokens for deactivated users and tokens issued before a revocation.
    if user is None or not user.is_active or user.token_version != claims.token_version:
        raise _UNAUTHORIZED
    path = request.url.path.removeprefix(settings.api_prefix)
    if user.role == Role.ANNOTATOR and (request.method, path) not in ANNOTATOR_ROUTES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    if (
        user.role.value in settings.two_factor_roles
        and not user.two_factor_enabled
        and (request.method, path) not in TWO_FACTOR_SETUP_ROUTES
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Set up two-factor sign-in on your account page first.",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: Role) -> Callable[[User], User]:
    """Dependency factory: allow only users holding one of the given roles."""
    allowed = frozenset(roles)

    def checker(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return user

    return checker


def client_ip(request: Request) -> str | None:
    """The browser's address. Requests from the frontend server carry it in
    X-Forwarded-For; the last entry is the one that server added, so it is used (earlier
    entries can be anything a browser sent)."""
    peer = request.client.host if request.client else None
    forwarded = request.headers.get("x-forwarded-for")
    if peer and forwarded and app_settings(request).trust_forwarded_from_private:
        try:
            trusted = ipaddress.ip_address(peer)
            last = forwarded.split(",")[-1].strip()
            if (trusted.is_private or trusted.is_loopback) and last:
                return str(ipaddress.ip_address(last))
        except ValueError:
            pass
    return peer


def too_many(exc: TooManyAttemptsError) -> HTTPException:
    """429 with Retry-After, for a rate limit that was reached (app/services/throttle)."""
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS, str(exc), headers={"Retry-After": str(exc.retry_after)}
    )


def limit(
    db: Session, kind: str, *, key: str | None = None, ip: str | None = None, count: bool = True
) -> None:
    """Refuse with 429 when the limit is reached; otherwise count this attempt."""
    try:
        throttle.check(db, kind, key=key, ip=ip)
    except TooManyAttemptsError as exc:
        raise too_many(exc) from None
    if count:
        throttle.record(db, kind, key=key, ip=ip)
