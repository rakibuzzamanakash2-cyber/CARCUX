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

- **Add a link** (Public signals, and an event's Evidence tab): paste a Facebook post, YouTube video, X post or news article with what it says. CARCUX reads the platform, post and account from the address (it never opens the link), says if the post is already in CARCUX, files it under its page or channel, and can link it to the event at once (supports, contradicts, related).
- **CARCUX's reading** (stance): wherever an item can be linked (possibly related reports and signals, suggested events, the review queue, the add-link form), CARCUX says how it reads the item (contradicts, partly supports, related only, not this event, supports) with its reason and how sure, and marks that option with a dashed outline. It never chooses for the analyst; the add-link form has no default. On the Evidence tab an item whose label differs from CARCUX's reading says **CARCUX reads it differently**; the History tab says whether the reading was followed. Second-opinion judges never see it.
- **Not this event, but true elsewhere:** an item labelled **Not this event** offers **Find its event**: the events it is already linked to, events that match its place and time (with CARCUX's reading) to link it there in one click, and **Create an event from it**. It stays *not this event* where it is: one item can be evidence for several events.
- **Copies** on an event's Evidence tab: an item that repeats another source's (same photo, same words, "share korlam …") says so, with why; analysts **Confirm**, say **Not a copy**, **Undo**, or **Mark as a copy of another item…** by hand. Copies are counted once in the suggested assessment, which says how many were.
- **Details in the text** on each report's and signal's page: deaths, people affected, how bad, cause, situation and denials found automatically, each with the words it came from, to check against the text.
- **Suggested assessment** on each event's overview (analysts, admins): a label, how likely it happened, the sources weighed most (each with how often it has been right, from its own record or assumed for its kind), details in dispute, and what the sources say about each detail (the estimate, "sources disagree" when credible ones differ, and each source's value with its words), with **Set to …** to take it. It comes from starting assumptions about each kind of source until an admin trains the assessment model on events with ground truth. Changing the assessment records the suggestion and whether it was followed; the event's History shows "(as suggested)" or what was suggested.
- Suggested events come from the 5 km / 48 h rule until an admin trains the suggestion model, then from the model; the list says which. In model mode each suggestion shows a match percentage and why: how similar the wording is, how long before or after the event's latest evidence, how far, same type. Linking from a suggestion records which one it was (rank, score, model) in the audit log. Analysts decide.
- Closing an event (resolved or dismissed) records its end time; reopening clears it.
- Assessment labels and their meanings are the CARCUX-BD dataset's, shown under the selector.

## Public signals and sources

| Page | Who | What |
|---|---|---|
| `/signals` | everyone | Alerts, bulletins and news collected from public sources. Tiles (last 24 hours, severe alerts, new, feeds working), search, filters for source, kind and status. |
| `/signals/{id}` | everyone; reviewers see more | What it says (excerpt and a link to the original), where and when, and **why it is here** (matched words, the place as written). Reviewers get **Triage** and **Events**: events it may be about with one-click linking, and **Create an event from it**. |
| `/signals/new` | analyst, admin | **Enter a bulletin** by hand for BMD, FFWC and other publishers without a feed, placed by district. |
| `/signals/import` | analyst, admin | **Import a list of past news** (CSV): **Check the file** shows each row as will add, already in, or needs fixing (with the reason), saving nothing; then **Import N items**. A template and the column meanings are on the page. |
| `/sources` | analyst, admin | Each source with how and how often it is read, the last read or the reason it failed, and signal counts. Admins **Read now**, **Switch off/on**, **Add a news feed** and **Fill in a past period** (GDACS or ReliefWeb archive, with case-study presets such as Cyclone Remal, May 2024). Desktop only. |
| `/` | everyone | **Public signals** layer: placed signals from the last 72 hours as rings coloured by severity (blue when not rated). |
| `/events/{id}` | analyst, admin | The Evidence tab lists linked signals beside reports, plus **Possibly related signals**. |

## Dataset work

| Where | Who | What |
|---|---|---|
| Event overview, **Ground truth** | analyst, admin | Did it happen (not established, yes, no), sources published afterwards (link, date, kind) and a note. Says whether the event is ready for the dataset. |
| Event Evidence tab | analyst, admin | Each link shows relation, **how sure** (unsure, fairly sure, certain) and **out of date when published**. Choosing **Partly supports**, when linking or changing, asks **what it gets wrong** (place, times, how bad, counts, cause, kind). |
| `/dataset` | analyst, admin; download admin | Events ready out of all, observations, labelled links, and lists of what to fix, each linking to the event. Admins download the zip (or include unlinked items). Desktop only. |
| `/dataset`, **Event suggestions** | analyst, admin; train admin | Whether suggestions use the rule or the model; the model's held-out results next to the rule's (first suggestion right, right one in the first three); how many links exist and how many were made from the first suggestion. Admins **Train and switch on**, **Retrain**, or go back to the rule. |
| `/dataset`, **Assessment suggestions** | analyst, admin; train admin | Starting assumptions or the trained model; the model's held-out Brier score next to the starting assumptions' and majority vote's; how many events have ground truth; how many assessments were set with a suggestion in view and how many followed it. Admins **Train and switch on**, **Retrain**, or go back to the starting assumptions. |

## Second opinions

| Page | Who | What |
|---|---|---|
| `/annotation` | analyst, admin | **Judge:** links waiting for your independent label, showing the event (with its ground truth) and the item, but not the label already given, and with no links to pages that would show it. You answer the guideline's decision procedure (5.1) in order, with conflicts, how sure and out of date. **Agreement:** Cohen's κ against the 0.70 target, Krippendorff's α, the confusion table, and disagreements to decide into a final label. Sidebar badge: links waiting for you. Desktop only. |
| `/events/{id}` Evidence tab | analyst, admin | Each link says whether it is waiting for a second opinion, agreed, disagreed (with a link to decide) or decided. **Not this event** is a new link label. |

## Review queue, audit log and account

| Page | Who | What |
|---|---|---|
| `/review` | analyst, admin | Reports nobody has triaged, oldest first, 10 per page. Each card shows the report, photos and flags with their meaning, plus up to three nearby open events to link it to in one click. **Mark reviewed**, **Dismiss** (a reason is required) or **Create an event from it**. Linking a report also marks it reviewed. A "Show" filter limits the queue to flagged reports. The sidebar badge and header bell show how many are waiting. |
| `/field-reports/{id}` | analyst, admin | A **Triage** panel on the overview with the same actions, and the reviewer, time and note once triaged. **Reopen** puts it back in the queue. |
| `/audit` | admin | Every recorded action in plain words, newest first, 50 per page. Filter by group or exact action, period (24 h, 7 days, 30 days) and the id of an event, report or account. Rows link to the event or report, and the full record opens under **Full record**. |
| `/account` | everyone | Profile, and **Change password** (current password, new one twice, at least 12 characters). This device stays signed in; every other device is signed out. |
| `/users` | admin | **Reset password** on each row sets a temporary password and signs that person out everywhere. |

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

Built from the reference mock-ups: a night-green frame around a light workspace, with Bangladesh drawn into it.

- **Frame:** dark header (logo on dark with the tagline, live counts, Dhaka date and time, account menu, review bell) and a dark sidebar with counts that need attention (critical/high events in red, reports to review in amber) and Sundarbans mangroves with a tiger fading in at the bottom.
- **Situation map:** night style. Bangladesh in green with white division lines and blue rivers, a scale bar and north arrow, and event cards with type icons, priority pills and time since start.
- **Pages:** each opens with a banner drawn from the country (`public/art/`, built by `scripts/build-art.py`): the Sundarbans with a Royal Bengal tiger and a nouka (events, sign-in), paddy fields with a farmer, a water buffalo and egrets (field reports), the misty Chittagong Hill Tracts with a hilltop kyang (users, review, audit), and the Padma at sunset with sail boats and a river dolphin (detail pages). Then figure tiles with icons, a search and filter bar, and tables with type icons, people's initials, pills and an open button per row. Detail pages use tabs.
- **Colour:** the logo's green for structure and actions, its red for what is critical; amber high, blue medium.
- **Type:** Source Sans 3, with Hind Siliguri for Bangla. Self-hosted from npm (SIL OFL). **Icons:** lucide-react.
- **Logo:** `public/carcux-logo-on-dark.png` (white letters, green leaf C, red stroke) for dark surfaces; `public/carcux-logo.png` for light ones; `src/app/icon.png` is the leaf C.
- **Credits:** some scene outlines are from game-icons.net (CC BY 3.0); see `public/art/CREDITS.txt`.
