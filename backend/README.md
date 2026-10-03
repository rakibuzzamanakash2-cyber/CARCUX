# CARCUX backend

FastAPI service for accounts, field reports, events, evidence and the audit log.

## Run the full stack (Docker, easiest)

From the repository root:

```bash
docker compose -f deployment/docker-compose.yml up --build
```

This starts PostgreSQL + PostGIS (5432), Redis (6379) and the API (8000), and applies database migrations on start-up. Then create the first admin:

```bash
docker compose -f deployment/docker-compose.yml exec backend python -m app.cli create-admin --email you@example.com --name "Your Name"
```

## Run locally (Python)

Needs a running PostgreSQL (e.g. `docker compose -f deployment/docker-compose.yml up db`).

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
python -m app.cli create-admin --email you@example.com --name "Your Name"
uvicorn app.main:app --reload
```

Open http://localhost:8000/docs, call `POST /api/v1/auth/login`, then click **Authorize** and paste the token.

## Accounts and roles

| Role | Can |
|---|---|
| `admin` | Manage accounts (create, change role, deactivate) |
| `analyst` | Read and verify all field reports; create and manage events and their evidence |
| `field_worker` | Submit field reports and read their own |
| `viewer` | Read events (read-only) |

- Passwords are hashed with Argon2id, minimum 12 characters.
- Login returns a short-lived bearer token (30 minutes by default).
- Changing a user's role or deactivating them revokes their existing tokens immediately.
- The last active admin cannot be demoted or deactivated.

## Field reports

Field workers submit what they saw; analysts and admins review.

| Endpoint | Who | What |
|---|---|---|
| `POST /api/v1/field-reports` | field worker, admin | Submit (multipart form, up to 4 JPEG/PNG/WebP photos, 8 MB each) |
| `GET /api/v1/field-reports` | field worker (own), analyst, admin | List, newest first; `?flagged=true` for reports with integrity flags; `?since=` (with UTC offset) for recent ones; `?q=` words in the text or place |
| `GET /api/v1/field-reports/{id}` | same | One report |
| `GET /api/v1/field-reports/{id}/media/{media_id}` | same | A photo |
| `GET /api/v1/field-reports/{id}/verify` | analyst, admin | Check the report has not been changed since submission |

- **Offline-safe:** the device sends a `client_report_id` it generated. Sending the same report again returns the original (200) instead of a duplicate; reusing the id for different content is refused (409).
- **Tamper-evident:** at submission the server stores a SHA-256 hash over the report's content and every photo. `verify` recomputes it and reports any edited text, moved location, or changed or missing photo. This detects changes; it cannot prevent someone with full server access from changing data *and* the hash, which is why verifications are audit-logged and the hash can later be anchored externally.
- **Integrity flags** (for human review, never blocking): `photo_reused` (identical or near-identical to an earlier report's photo), `impossible_travel` (faster than 150 km/h between a worker's reports), `observed_in_future`, `old_observation` (over 24 h), `submission_burst`, `poor_location_accuracy`.
- **Privacy:** someone else's report returns 404, exactly like a missing one. Photos are checked by decoding (not by file name), stored outside the database, and served with `no-store` caching.
- **Photos on disk:** `CARCUX_MEDIA_DIR` (Docker: the `media_data` volume). Back it up together with the database.

## Events and evidence

An event is the working record of one real situation ("Waterlogging at Mirpur 10 circle"). Field reports attach to it as **evidence**, each with a relation: `supports`, `partially_supports`, `contradicts` or `related`. Labels match the CARCUX-BD dataset, so analysts' decisions can later be compared with gold annotations and with the fusion engine.

| Endpoint | Who | What |
|---|---|---|
| `GET /api/v1/events` | everyone signed in | List, newest first; `?status=active&status=monitoring`, `?family=urban_emergency`, `?priority=critical&priority=high`, `?q=` words in title, place or summary |
| `POST /api/v1/events` | analyst, admin | Create; `field_report_ids` attaches reports as supporting evidence |
| `GET /api/v1/events/{id}` | everyone signed in | One event with evidence counts (by relation, distinct reporters, photos) |
| `PATCH /api/v1/events/{id}` | analyst, admin | Change title, type, place, times, status, priority, assessment |
| `GET /api/v1/events/{id}/history` | analyst, admin | Who changed what, from the audit log |
| `GET/POST /api/v1/events/{id}/evidence` | analyst, admin | List or link a report (409 if already linked) |
| `PATCH/DELETE /api/v1/events/{id}/evidence/{evidence_id}` | analyst, admin | Change the relation or note, or unlink |
| `GET /api/v1/events/{id}/candidate-reports` | analyst, admin | Unlinked reports that may belong to the event |
| `GET /api/v1/field-reports/{id}/events` | analyst, admin | Events a report is evidence for |
| `GET /api/v1/field-reports/{id}/candidate-events` | analyst, admin | Events a report may belong to |

- **Status:** `active`, `monitoring`, `resolved`, `dismissed`. **Priority:** `low` to `critical`. **Assessment:** the dataset's six labels, from `verified` to `insufficient_evidence`; new events start `unverified`.
- **Matching is a baseline, and only a suggestion:** within 5 km, and the report falls within 48 h of the event's time span (an open event runs until now). Same type first, then nearest. The correlation engine in `ai/correlation/` will replace it and can be scored against analysts' links.
- Linking a report marks it `reviewed`. Every create, change, link, relation change and unlink is audit-logged with old and new values.

## Overview

`GET /api/v1/overview` (everyone signed in) feeds the console's status bar: open events by priority and reports observed in the last 24 hours (a field worker's own). Analysts and admins also get flagged reports in the last 24 hours and the number of reports nobody has reviewed yet; for others those are `null`.

## Audit log

Logins (success and failure), account creation and changes, field report submissions and verifications, and every event and evidence change are written to `audit_log`. The table is **append-only**: a database trigger rejects every UPDATE and DELETE.

## Database migrations

```bash
alembic revision --autogenerate -m "describe the change"   # after changing models
alembic upgrade head
alembic check                                              # fails if models and migrations differ
```

Always review an autogenerated migration before committing it.

## Checks

```bash
ruff check .
ruff format --check .
pytest
```

Tests need PostgreSQL. They use `CARCUX_TEST_DATABASE_URL`, default `postgresql+psycopg://carcux:carcux@127.0.0.1:5432/carcux_test`. CI runs the same checks plus `alembic check`.

## Layout

```
backend/
├── app/
│   ├── main.py          # application factory
│   ├── cli.py           # command-line tasks (create-admin)
│   ├── core/            # settings, password hashing, tokens
│   ├── db/              # base model, engine and sessions
│   ├── models/          # database tables
│   ├── schemas/         # request and response models
│   ├── services/        # business logic shared by API and CLI
│   └── api/             # routers and dependencies
├── migrations/          # Alembic migrations
└── tests/
```
