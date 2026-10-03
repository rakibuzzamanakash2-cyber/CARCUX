# CARCUX frontend

Next.js (App Router) console for CARCUX staff: a command-center layout that opens on the situation map, with events, field reports and account management. Sections whose backend is not built yet (review queue, audit log) show what they will do.

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

## Situation map (home page)

- **Layout:** white header with the logo and a status line (critical, high and open events; reports in 24 h; for reviewers also flagged and to-review counts; Dhaka clock); forest-green sidebar (a tab bar on phones); the map and the open-events list as two cards.
- **Markers:** colour is priority (red critical, amber high, blue medium, grey low); shape is the kind of event (circle natural calamity, diamond road and infrastructure, triangle urban emergency), so they read without colour too. Critical events pulse: the one animation in the console, off when the system asks for reduced motion.
- **Selecting** a marker or a list item flies the map to it and opens its card with priority, assessment, evidence and **Open event**. The kind filter narrows list and markers together.
- **Field reports** from the last 48 hours show as small dots for analysts and admins (green, red if flagged); click one to open it. Field workers get a **New report** button instead.
- **Works offline.** The basemap (Bangladesh, divisions, major rivers, cities, neighbours) is a 107 KB GeoJSON built from Natural Earth (public domain) by `scripts/build-basemap.py`, served from `public/geo/`. **Street detail** adds OpenStreetMap/CARTO tiles when there is internet.

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
| `/events` | everyone | Tiles (open, critical or high, verified, new today), search, filters for status, kind and priority, and a table with priority, assessment, evidence, status and start. |
| `/events/new` | analyst, admin | Create an event. From a report (`?from_report=`), type, place, location and time are prefilled and the report is attached as support. |
| `/events/{id}` | everyone; reviewers see more | Overview (summary, details) for all. Reviewers also get **Analyst decision** on the overview, an **Evidence** tab (linked reports with relation and unlink; possibly related reports with one-click linking) and a **History** tab in plain words. |
| `/field-reports/{id}` | analyst, admin | An **Events** tab: events the report is linked to, open events nearby to link it to, and **Create an event from this report**. |

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
├── components/              # shared UI (rail, status bar, page header, form fields, badges)
└── app/
    ├── login/               # sign-in page
    ├── actions/             # Server Actions: login, logout, users, field reports, events
    ├── fonts/               # self-hosted Archivo (SIL OFL)
    └── (console)/           # signed-in shell: status bar, rail
        ├── page.tsx         # situation map (map-view.tsx: Leaflet; situation.tsx: panel)
        └── (paged)/         # events, field reports, users, and upcoming sections
```

## Design

The logo's green and red on a light, official workspace, like the flag.

- **Green carries the structure and main actions:** forest-green sidebar, the green band that opens every page, green buttons and links (`#0b7a33`, the logo green darkened for contrast).
- **Red is the accent:** the stripe under the header, the rule under each page band, the active menu mark and tab underline, the short underline under section titles, secondary buttons (red outline) and key figures. It also marks what is critical. Amber is high priority; blue is medium on the map.
- **Page structure:** green band (title, purpose, main action) → figure tiles → filter bar (search + dropdowns) → table. Detail pages use tabs (`?tab=`): events have Overview, Evidence and History; field reports have Overview, Integrity and Events. Building blocks live in `src/components/page-header.tsx` (`PageBand`, `PageBody`, `Panel`, `StatTile`, `Tabs`), `filter-bar.tsx` and `data-table.tsx`.
- **Type:** Source Sans 3 for the interface, Hind Siliguri for Bangla. Self-hosted from npm (`@fontsource*`, SIL OFL).
- **Logo:** `public/carcux-logo.png` (transparent background); `src/app/icon.png` is the leaf C. **Icons:** lucide-react.
