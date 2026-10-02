"""Password hashing (Argon2id) and access tokens (JWT)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import Settings

_hasher = PasswordHasher()  # Argon2id with library-recommended parameters

# Used to spend the same time on unknown emails as on wrong passwords,
# so response timing does not reveal which accounts exist.
_DUMMY_HASH = _hasher.hash("carcux-timing-equaliser")

MIN_PASSWORD_LENGTH = 12


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """Check a password. Pass None for an unknown account: it still costs one hash."""
    if password_hash is None:
        try:
            _hasher.verify(_DUMMY_HASH, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            pass
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


@dataclass(frozen=True)
class TokenClaims:
    user_id: uuid.UUID
    role: str
    token_version: int


class InvalidTokenError(Exception):
    pass


def create_access_token(
    settings: Settings, user_id: uuid.UUID, role: str, token_version: int
) -> tuple[str, int]:
    """Return (token, lifetime_seconds)."""
    now = datetime.now(UTC)
    lifetime = timedelta(minutes=settings.access_token_minutes)
    payload = {
        "sub": str(user_id),
        "role": role,
        "ver": token_version,
        "type": "access",
        "iat": now,
        "exp": now + lifetime,
        "jti": uuid.uuid4().hex,
    }
    token = jwt.encode(
        payload, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm
    )
    return token, int(lifetime.total_seconds())


def decode_access_token(settings: Settings, token: str) -> TokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp", "iat", "ver", "type"]},
        )
        if payload["type"] != "access":
            raise InvalidTokenError("wrong token type")
        return TokenClaims(
            user_id=uuid.UUID(payload["sub"]),
            role=str(payload.get("role", "")),
            token_version=int(payload["ver"]),
        )
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise InvalidTokenError(str(exc)) from exc
