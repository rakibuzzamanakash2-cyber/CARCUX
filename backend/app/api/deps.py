"""Shared request dependencies: database session, current user, role checks."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, app_settings
from app.core.security import InvalidTokenError, decode_access_token
from app.db.session import get_db
from app.models.user import Role, User

_bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(app_settings)]

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
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
    return request.client.host if request.client else None
