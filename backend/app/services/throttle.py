"""Rate limits on attempts that an attacker would repeat: sign-ins, sign-ups,
field-report submissions (Spec §11.2, MVP stage). Comments and opinions on the public
site have their own limits (app/services/public.py).

Each limit counts recent events of one kind, by a key (a keyed hash of the email or
account, so this table never holds an email) and/or the client's IP address. A limit
that is reached refuses the next attempt for the rest of its window, even with the
right password: that is what stops guessing.

Sign-in limits are per email *and* address (5 in 15 minutes: a person mistyping is not
hurt), per email from anywhere (20 an hour: slows guessing spread over many addresses,
at the cost that someone can delay one account's sign-in for up to an hour), and per
address (30 in 15 minutes: one machine trying many emails).

Addresses come from the frontend (app/api/deps.client_ip). With the browser talking to
the frontend directly, as in deployment/docker-compose.yml, the browser can choose the
address it claims, so only the per-email limits hold against a determined attacker. A
reverse proxy in front of the frontend that overwrites X-Forwarded-For with the real
address (nginx: `proxy_set_header X-Forwarded-For $remote_addr;`) makes the address
limits, and the addresses in the audit log, trustworthy too. That proxy belongs with
HTTPS in deployment hardening.
"""

import hashlib
import hmac
import math
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.throttle import ThrottleEvent

KEEP = timedelta(days=1)


@dataclass(frozen=True)
class Limit:
    by: str  # "key", "ip" or "both"
    count: int
    window: timedelta


STAFF_LOGIN = "staff_login_failed"
PUBLIC_LOGIN = "public_login_failed"
PASSWORD_CHECK = "password_check_failed"  # noqa: S105 (a name, not a password)
SIGNUP = "public_signup"
TWO_FACTOR = "two_factor_failed"
FIELD_REPORT = "field_report"

_SIGN_IN = (
    Limit("both", 5, timedelta(minutes=15)),
    Limit("key", 20, timedelta(hours=1)),
    Limit("ip", 30, timedelta(minutes=15)),
)
LIMITS: dict[str, tuple[Limit, ...]] = {
    STAFF_LOGIN: _SIGN_IN,
    PUBLIC_LOGIN: _SIGN_IN,
    # The current password, asked again by a signed-in session (change password, delete).
    PASSWORD_CHECK: (Limit("key", 5, timedelta(minutes=15)),),
    # Wrong authenticator or recovery codes, per account: a million codes cannot be
    # tried five at a time.
    TWO_FACTOR: (Limit("key", 5, timedelta(minutes=15)),),
    # Each sign-up may send an email.
    SIGNUP: (Limit("ip", 5, timedelta(hours=1)), Limit("key", 3, timedelta(hours=1))),
    # Far above a real worker's pace; the submission_burst flag catches less.
    FIELD_REPORT: (Limit("key", 60, timedelta(minutes=10)),),
}


class TooManyAttemptsError(Exception):
    def __init__(self, retry_after: int):
        super().__init__(f"Too many attempts. Try again in {wait_text(retry_after)}.")
        self.retry_after = retry_after


def wait_text(seconds: int) -> str:
    minutes = max(math.ceil(seconds / 60), 1)
    return "1 minute" if minutes == 1 else f"{minutes} minutes"


def key_for(settings: Settings, value: str) -> str:
    """A keyed hash of an email or account id: stable, but not reversible by guessing
    emails without the server's secret."""
    secret = settings.jwt_secret.get_secret_value().encode()
    return hmac.new(secret, value.strip().lower().encode(), hashlib.sha256).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def check(db: Session, kind: str, *, key: str | None = None, ip: str | None = None) -> None:
    """Raise TooManyAttemptsError if any of this kind's limits is reached."""
    now = _now()
    wait = 0
    for limit in LIMITS[kind]:
        q = select(func.count(), func.min(ThrottleEvent.at)).where(
            ThrottleEvent.kind == kind, ThrottleEvent.at > now - limit.window
        )
        if limit.by in ("key", "both"):
            if key is None:
                continue
            q = q.where(ThrottleEvent.key == key)
        if limit.by in ("ip", "both"):
            if ip is None:
                continue
            q = q.where(ThrottleEvent.ip == ip)
        n, oldest = db.execute(q).one()
        if n >= limit.count:
            # Free again once enough of the counted attempts have aged out; the oldest
            # one leaving is a fair, simple estimate.
            wait = max(wait, int((oldest + limit.window - now).total_seconds()) + 1)
    if wait:
        raise TooManyAttemptsError(wait)


def record(db: Session, kind: str, *, key: str | None = None, ip: str | None = None) -> None:
    """Count one attempt (the caller commits). Old rows are cleared now and then."""
    db.add(ThrottleEvent(kind=kind, key=key, ip=ip, at=_now()))
    if secrets.randbelow(50) == 0:
        db.execute(delete(ThrottleEvent).where(ThrottleEvent.at < _now() - KEEP))


def clear(db: Session, kind: str, *, key: str, ip: str | None) -> None:
    """Forget the failures from this email and address after a successful sign-in."""
    db.execute(
        delete(ThrottleEvent).where(
            ThrottleEvent.kind == kind, ThrottleEvent.key == key, ThrottleEvent.ip == ip
        )
    )
