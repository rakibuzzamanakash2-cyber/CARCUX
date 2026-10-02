# CARCUX frontend

Next.js (App Router) console for CARCUX staff: sign-in, overview, account management, field reports and events. Sections whose backend is not built yet (map, review queue, audit log) show what they will do.

## Run locally

Needs the backend running (see `../backend/README.md`).

```bash
cd frontend
npm install
npm run dev          # http://localhost:3000
```

The backend address is read on the server only, from `CARCUX_API_URL` (default `http://localhost:8000/api/v1`). Put it in `frontend/.env.local` if yours differs.

Or run everything with Docker from the repository root:

```bash
docker compose -f deployment/docker-compose.yml up --build
```

## How sign-in works

- The login form posts to a **Server Action**, which calls the backend and stores the access token in an **httpOnly cookie**. Browser JavaScript can never read the token.
- `src/proxy.ts` sends visitors without a session cookie to `/login` (fast, optimistic check).
- `src/lib/dal.ts` is the real check: every protected page asks the backend who the user is, so expired, deactivated or re-roled accounts are stopped on their next click.
- Every Server Action re-checks the user's role. Server Actions are public endpoints, so hiding a button is never enough.
- The `?next=` redirect after login only accepts paths on this site.

## Field reports

| Page | Who | What |
|---|---|---|
| `/field-reports` | field worker (own), analyst, admin | List, newest first. Reviewers get an **All / Flagged** filter and flag badges. |
| `/field-reports/new` | field worker, admin | Phone-first form: text, event type, **Use my location** (GPS), Dhaka time, up to 4 photos with previews. |
| `/field-reports/{id}` | same as list | Text, details, photos, fingerprint. Reviewers also see each flag explained and a **Check it is unchanged** button. |

- **Safe to resend.** Each form load carries a fresh `client_report_id`. If the connection drops and the worker presses Send again, the backend returns the original report instead of storing a second copy.
- **Flags are for reviewers only.** Field workers never see integrity flags, so the checks cannot be learned and dodged.
- **Photos** are fetched through `/field-reports/{id}/photos/{mediaId}`, a route handler that adds the session token; the backend decides who may see each photo. They are never cached.
- **Upload size.** Up to 4 × 8 MB per report, so `next.config.ts` raises the Server Action body limit and the proxy body limit to 34 MB (the defaults, 1 MB and 10 MB, would reject or silently truncate photos).
- **Location needs HTTPS.** Browsers only share GPS with `https://` pages and `localhost`. On a phone opening the console over plain `http://` on your network, **Use my location** explains this and the worker types coordinates instead. A production deployment must serve HTTPS.
- **Event types** mirror the dataset schema; `npm run check:event-types` (run in CI) fails if they drift.

## Events

| Page | Who | What |
|---|---|---|
| `/` | everyone | Open events, most urgent first (priority, then newest). |
| `/events` | everyone | **Open / Resolved / Dismissed / All**, filter by kind. Priority, assessment, status and an evidence summary per event. |
| `/events/new` | analyst, admin | Create an event. From a report (`?from_report=`), type, place, location and time are prefilled and the report is attached as support. |
| `/events/{id}` | everyone; reviewers see more | Details and evidence counts for all. Reviewers also get **Analyst decision** (status, priority, assessment, edit title/place/summary), **Evidence** (change relation, unlink), **Possibly related reports** (one-click link as supports / partly supports / contradicts / related) and **History** in plain words. |
| `/field-reports/{id}` | analyst, admin | An **Events** section: events the report is linked to, open events nearby to link it to, and **Create an event from this report**. |

- Suggestions come from place and time only (5 km, 48 h); the page says so. Analysts decide.
- Closing an event (resolved or dismissed) records its end time; reopening clears it.
- Assessment labels and their meanings are the CARCUX-BD dataset's, shown under the selector.

## Checks

```bash
npm run lint
npx tsc --noEmit
npm run check:event-types
npm run build
```

CI runs the same commands.

## Layout

```
src/
├── proxy.ts                 # redirect to /login when there is no session cookie
├── lib/                     # backend client, session cookie, auth checks (server-only); formatting, event types (shared)
├── components/              # shared UI (sidebar, form fields, placeholders)
└── app/
    ├── login/               # sign-in page
    ├── actions/             # Server Actions: login, logout, users, field reports, events
    ├── fonts/               # self-hosted Archivo (SIL OFL)
    └── (console)/           # signed-in pages: overview, users, field reports, events, and upcoming sections
```

## Design

Dark console matching the CARCUX logo. Red is a signal, never decoration: it marks the current page, priority and errors. One typeface (Archivo) in two widths: condensed for headings, normal for reading.
