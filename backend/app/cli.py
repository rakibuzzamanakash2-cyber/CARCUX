"""Command-line tasks.

Create the first admin account (prompts for the password):

    python -m app.cli create-admin --email you@example.com --name "Your Name"

Read public sources (GDACS, news feeds, ReliefWeb):

    python -m app.cli ingest --once            # every enabled source that is due
    python -m app.cli ingest --source gdacs    # one source, now
    python -m app.cli ingest --loop            # forever (the ingest worker container)

Export the CARCUX-BD dataset (JSON Lines, validated with data/tools):

    python -m app.cli export-dataset out/            # events with ground truth, linked items
    python -m app.cli export-dataset out/ --all      # also every unlinked report and signal
"""

import argparse
import getpass
import logging
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


def ingest(once: bool, source_key: str | None, loop_forever: bool) -> int:
    from sqlalchemy import select

    from app.ingest import runner
    from app.models.signal import Source

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    try:
        if loop_forever:
            runner.loop(factory, settings)
        if source_key:
            with factory() as db:
                source = db.scalar(select(Source).where(Source.key == source_key))
                if source is None:
                    print(f"No source with key {source_key!r}.", file=sys.stderr)
                    return 1
                try:
                    run = runner.run_source(db, source, settings)
                except runner.NotReadableError:
                    print(f"{source_key} is entered by hand; nothing to fetch.", file=sys.stderr)
                    return 1
                print(
                    f"{source_key}: ok={run.ok} fetched={run.fetched} new={run.created} "
                    f"updated={run.updated} skipped={run.skipped} {run.error or ''}"
                )
                return 0 if run.ok else 1
        if once:
            runs = runner.run_due(factory, settings)
            print(f"Read {len(runs)} source(s); {sum(not r.ok for r in runs)} failed.")
            return 0 if all(r.ok for r in runs) else 1
    finally:
        engine.dispose()
    return 2


def export_dataset(directory: str, include_unlinked: bool) -> int:
    import json
    from pathlib import Path

    from app.services import dataset

    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    engine = make_engine(get_settings().database_url)
    with make_session_factory(engine)() as db:
        data = dataset.build(db, include_unlinked=include_unlinked)
        audit.record(
            db,
            audit.AuditAction.DATASET_EXPORTED,
            details={"counts": data.manifest["counts"], "via": "cli"},
        )
        db.commit()
    engine.dispose()
    for name, rows in data.files.items():
        (out / name).write_text(dataset.write_jsonl(rows), encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps(data.manifest, indent=2, ensure_ascii=False))
    (out / "problems.json").write_text(
        json.dumps([p.__dict__ for p in data.problems], indent=2, ensure_ascii=False)
    )
    (out / "id_map.json").write_text(json.dumps(data.id_map, indent=2))
    for name, n in data.manifest["counts"].items():
        print(f"{name}: {n}")
    if data.problems:
        print(f"{len(data.problems)} record(s) left out; see problems.json")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create-admin", help="create an admin account")
    p.add_argument("--email", required=True)
    p.add_argument("--name", required=True)
    p = sub.add_parser("ingest", help="read public sources into signals")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="every enabled source that is due")
    mode.add_argument("--source", help="one source by key, now (e.g. gdacs)")
    mode.add_argument("--loop", action="store_true", help="run due sources every minute")
    p = sub.add_parser("export-dataset", help="write the CARCUX-BD dataset files")
    p.add_argument("directory")
    p.add_argument("--all", action="store_true", help="include unlinked reports and signals")
    args = parser.parse_args(argv)

    if args.command == "create-admin":
        return create_admin(args.email, args.name)
    if args.command == "export-dataset":
        return export_dataset(args.directory, args.all)
    if args.command == "ingest":
        return ingest(args.once, args.source, args.loop)
    return 2


if __name__ == "__main__":
    sys.exit(main())
