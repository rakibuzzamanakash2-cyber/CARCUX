# CARCUX frontend

Next.js (App Router) console for CARCUX staff: sign-in, overview, and account management. Sections whose backend is not built yet (map, events, field reports, review queue, audit log) show what they will do.

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

## Checks

```bash
npm run lint
npx tsc --noEmit
npm run build
```

CI runs the same three commands.

## Layout

```
src/
├── proxy.ts                 # redirect to /login when there is no session cookie
├── lib/                     # server-only: backend client, session cookie, auth checks
├── components/              # shared UI (sidebar, form fields, placeholders)
└── app/
    ├── login/               # sign-in page
    ├── actions/             # Server Actions: login, logout, users
    ├── fonts/               # self-hosted Archivo (SIL OFL)
    └── (console)/           # signed-in pages: overview, users, and upcoming sections
```

## Design

Dark console matching the CARCUX logo. Red is a signal, never decoration: it marks the current page, priority and errors. One typeface (Archivo) in two widths: condensed for headings, normal for reading.
