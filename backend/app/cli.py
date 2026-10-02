"""Command-line tasks.

Create the first admin account (prompts for the password):

    python -m app.cli create-admin --email you@example.com --name "Your Name"
"""

import argparse
import getpass
import sys

from app.core.config import get_settings
from app.core.security import MIN_PASSWORD_LENGTH
from app.db.session import make_engine, make_session_factory
from app.models.user import Role
from app.services import audit
from app.services.users import EmailAlreadyRegisteredError, create_user, normalise_email


def create_admin(email: str, name: str) -> int:
    try:
        email = normalise_email(email)
    except ValueError as exc:
        print(f"Invalid email {email!r}: {exc}", file=sys.stderr)
        return 1
    password = getpass.getpass("Password: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", file=sys.stderr)
        return 1
    if getpass.getpass("Repeat password: ") != password:
        print("Passwords do not match.", file=sys.stderr)
        return 1

    engine = make_engine(get_settings().database_url)
    with make_session_factory(engine)() as db:
        try:
            user = create_user(
                db,
                email=email,
                full_name=name,
                password=password,
                role=Role.ADMIN,
                actor_id=None,
                action=audit.AuditAction.USER_BOOTSTRAPPED,
            )
        except EmailAlreadyRegisteredError:
            print(f"An account for {email} already exists.", file=sys.stderr)
            return 1
        db.commit()
        print(f"Admin created: {user.email} ({user.id})")
    engine.dispose()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create-admin", help="create an admin account")
    p.add_argument("--email", required=True)
    p.add_argument("--name", required=True)
    args = parser.parse_args(argv)

    if args.command == "create-admin":
        return create_admin(args.email, args.name)
    return 2


if __name__ == "__main__":
    sys.exit(main())
