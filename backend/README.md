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
| `GET /api/v1/field-reports` | field worker (own), analyst, admin | List, newest first; `?flagged=true` for reports with integrity flags; `?since=` (with UTC offset) for recent ones; `?q=` words in the text or place; `?status=submitted&order=oldest` for a review queue |
| `GET /api/v1/field-reports/{id}` | same | One report |
| `GET /api/v1/field-reports/{id}/media/{media_id}` | same | A photo |
| `GET /api/v1/field-reports/{id}/verify` | analyst, admin | Check the report has not been changed since submission |
| `POST /api/v1/field-reports/{id}/review` | analyst, admin | Triage: `reviewed`, `dismissed` (a reason is required) or back to `submitted`; records who and when |

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
- **Matching is only a suggestion.** Until a suggestion model is trained: within 5 km, and the report falls within 48 h of the event's time span; same type first, then nearest. An event without an end time runs until a week after its latest linked item (or its start), never past now: a live event that keeps getting reports moves forward, while an old case study is not offered news from months later. Items labelled *not this event* do not extend it; an end time set by an analyst always wins. After training, see [Event suggestions](#event-suggestions).
- Linking a report marks it `reviewed`. Every create, change, link, relation change and unlink is audit-logged with old and new values.

## Public signals

Signals are evidence from outside CARCUX: disaster alerts, official bulletins and news items. They link to events like field reports do (`signal_id` instead of `field_report_id` when linking evidence), and their fields follow the CARCUX-BD observation schema.

| Source | How it is read | Notes |
|---|---|---|
| GDACS (EU JRC, UN OCHA) | RSS, every 30 min | Floods, tropical cyclones and earthquakes concerning Bangladesh, with coordinates and green, orange or red alert levels. CC BY 4.0, credit GDACS. |
| Prothom Alo (English, Bangla), The Daily Star | RSS, every 30 to 60 min | Kept only if keywords say it is a disaster or disruption **and** it names a place in Bangladesh. Headline, an excerpt of at most 300 characters and the link are stored, never the article. |
| ReliefWeb | API v2 | Off until you set `CARCUX_RELIEFWEB_APPNAME` (an approved app name) and enable it. Carries BMD and FFWC bulletins. |
| BMD, FFWC | Entered by hand | `POST /api/v1/signals` with a district or coordinates; the full bulletin text can be kept. |

- **Placing news.** `app/ingest/places.py` uses the extraction module's place finder (`app/extraction/places.py`, a checked copy of `ai/extraction`), which looks up names in `app/extraction/data/bd_gazetteer.json` (64 districts and 8 divisions with coordinates, 481 upazilas and 48 city localities; English, Bangla and Banglish spellings with case endings; districts and upazilas from [nuhil/bangladesh-geocode](https://github.com/nuhil/bangladesh-geocode), MIT). Names shared by several places are settled by the districts the text names. The first place mentioned anchors the item, refined to the most specific place in its district; precision is the uncertainty radius (2.5 km for a locality, 30 km for a district) and widens when the text names other districts too.
- **Fresh news only.** Feed items older than 7 days are left out (some feed addresses redirect to archives that stopped years ago).
- **Classifying news.** `app/ingest/classify.py` uses English and Bangla keywords per event type; it needs a match in the headline, or two in the summary. Matched words are stored in `extraction`, so each decision can be explained. Both are baselines for the learned models.
- **Matching signals to events:** the 5 km / 48 h rule, widened by the signal's precision (up to 300 km) and using its validity period; or the suggestion model once trained (see [Event suggestions](#event-suggestions)).
- **Fetching safely:** http(s) only, no private or local addresses, at most 3 redirects (each checked), 5 MB and 20 s limits, XML parsed with `defusedxml`.

| Endpoint | Who | What |
|---|---|---|
| `GET /api/v1/signals` | everyone signed in | Newest first; `?source=`, `?status=new`, `?family=`, `?event_type=`, `?q=`, `?since=`, `?located=true` |
| `POST /api/v1/signals` | analyst, admin | Enter a bulletin for a manual source (BMD, FFWC) |
| `GET /api/v1/signals/{id}` | everyone signed in | One signal |
| `POST /api/v1/signals/{id}/review` | analyst, admin | `new`, `reviewed`, or `dismissed` with a reason |
| `GET /api/v1/signals/{id}/events`, `/candidate-events` | analyst, admin | Events it is linked to; events it may be about |
| `GET /api/v1/events/{id}/candidate-signals` | analyst, admin | Signals that may be about the event |
| `GET /api/v1/sources` | analyst, admin | Sources with last run, last error and signal counts |
| `POST /api/v1/sources`, `PATCH /api/v1/sources/{id}` | admin | Add a news feed; rename, re-address, switch on or off, change interval |
| `POST /api/v1/sources/{id}/fetch`, `GET .../runs` | admin; analyst, admin | Read a source now; recent runs |
| `GET /api/v1/places/districts` | everyone signed in | Districts and their centres |

**Past periods (backfill).** For case studies, archives can be read for a period of up to a year: `POST /api/v1/sources/{id}/backfill` with `{start, end}` (admin), or `python -m app.cli backfill gdacs 2024-08-15 2024-09-10`. GDACS uses its event search API (floods, cyclones, earthquakes; ids match the live feed, so nothing is stored twice); ReliefWeb searches by the reports' original date. Each backfill is an ingest run with its period recorded; the live schedule is not touched.

**Importing a list of past news.** News archives have no feed that goes back in time, so annotators collect links in a CSV (`url, title, published, publisher` required; `excerpt, event_type, place, language, severity` optional) and upload it: `POST /api/v1/signals/import?dry_run=true` checks every row without saving, `dry_run=false` imports. Type and place are found from the headline when not given; publishers are matched by name or domain, or added. Only headline, excerpt (300 characters at most) and link are kept.

**The ingest worker.** `python -m app.cli ingest --loop` reads every enabled source when it is due (the `ingest` service in Docker Compose). `--once` reads what is due and exits; `--source gdacs` reads one source now.

## The CARCUX-BD dataset

Everything analysts do in CARCUX can be exported as the research dataset in `data/` (schema v1.1, guideline 0.2), and the export passes the dataset validator.

| Endpoint / command | Who | What |
|---|---|---|
| `GET /api/v1/dataset/summary` | analyst, admin | What an export would contain now, and what keeps records out (with event titles) |
| `GET /api/v1/dataset/export` | admin | Zip: the five JSON Lines files, `manifest.json`, `problems.json`, `id_map.json`. `?include_unlinked=true` adds reports and signals not linked to an exported event |
| `python -m app.cli export-dataset DIR [--all]` | server | The same, written to a directory |

- **Events go in once their ground truth is recorded:** `occurred` (yes or no) and at least one source published afterwards (`ground_truth_sources`: reference, published_at, kind), set with `PATCH /events/{id}`.
- **Links carry the dataset's labels:** `conflicts` (attributes the item gets wrong; required for `partially_supports`, not allowed for `related`), `stale`, and `confidence` 1 to 3.
- **Assessments at T+1h, T+6h, T+24h and final** are reconstructed from the audit log: the label set in CARCUX at each moment after the first linked item.
- **Pseudonymous:** annotators are `ANN-001`… in order of account creation, `ANN-000` is CARCUX's automatic checks; field workers appear as "Field worker" sources. Phone numbers and emails are removed from field report text. Names of private individuals cannot be found automatically: read field report text before publishing. Keep `id_map.json` private.
- Reused photos flagged at submission become `same_media` dependences. News stays an excerpt (300 characters at most).
- Validate an export: `cd data/tools && python -m carcux_data.validate <dir>`.

## Second opinions and agreement

The annotation guideline (section 7) asks for every link to be labelled independently by two annotators, agreement measured, and disagreements resolved into a gold label.

- **Judgements.** Each annotator's own label of a link is kept in `evidence_judgements`. Linking or relabelling records the linker's judgement; existing links became their linker's first judgement (migration 0008). The link's `relation` is the working label the console uses.
- **Blind queue.** `GET /api/v1/annotation/queue` lists links the current analyst has not judged and that have fewer than two judgements, oldest first, without anyone's label. `POST /api/v1/annotation/judgements` records (or replaces) theirs.
- **Agreement.** `GET /api/v1/annotation/agreement`: Cohen's κ on the first two judgements per link, Krippendorff's α (nominal, any number of annotators), percent agreement and the confusion table. Target κ ≥ 0.70 before scaling up.
- **Adjudication.** `GET /api/v1/annotation/disagreements` lists links whose judgements differ (in label, or in conflicts for partly supports); `POST /api/v1/annotation/adjudicate` records the gold label, which the working label then follows.
- **New label `unrelated`** ("not this event"): hard negatives for the model; not counted as evidence.
- **Export:** one annotation per annotator per relation; `gold` comes from adjudication, or from agreement when annotators agree.

## Event suggestions

Which existing events a report or signal most likely belongs to (`app/services/suggest.py`). This is the correlation research (`ai/correlation/`) in the product.

- **Two modes.** Without a trained model, the 5 km / 48 h rule above (baseline B2 of the research). With one, a wider search (50 km plus the item's location uncertainty, 14 days around the event; any distance for a signal with no place) ranked by a logistic model over the research's cluster-level features: wording similarity to the event's evidence (character n-grams, so Bangla, Banglish and English all work), time from the event's evidence span, distance to its nearest located evidence, type agreement, and the event's size. Suggestions under 5 % are not shown. Every candidate list says which mode made it (`method`), with `score`, `text_similarity` and `hours_from_latest` in model mode.
- **Training** (admin): `POST /api/v1/suggestions/model/train`, or `python -m app.cli train-suggestions`. It learns from every link analysts have made (gold labels where adjudicated; "not this event" links are negatives), and needs at least 20 linked reports or signals across 5 events. One event in five is held out first: the model and the rule rank the same candidates for those events' items, and the share where the right event comes first (and in the first three) is stored with the model. The final model is then fitted on everything and becomes the only active one.
- **Status:** `GET /api/v1/suggestions/model` (analyst, admin): mode, active model and its held-out results, previous models, how many links exist, and how often links were made from a suggestion. `POST /api/v1/suggestions/model/deactivate` (admin) returns to the rule.
- **Measured in use.** When an analyst links from a suggestion list, `POST /events/{id}/evidence` carries `suggestion: {rank, method, score, model_id}`, written into the `event.evidence_linked` audit entry. The status counts how many links came from the first suggestion.
- **Not in the blind queue.** Second-opinion annotators never see suggestions, so they cannot anchor on the model (and inflate agreement).
- Migration 0009 adds `suggestion_models` (weights, held-out metrics; at most one active).

## Assessment suggestions

How likely each event really happened, and which of the six assessment labels fits (`app/services/assess.py`). This is the fusion research (`ai/fusion/`, the proposed `reliability-dep` model and the six-label assessment) in the product.

- **Votes.** Each linked report or signal that supports or partly supports an event says it happened; one that contradicts it says it did not. Adjudicated relations are used where they exist. A source counts once per event, with its latest item, so a field worker's three reports or a feed's repeated bulletins are one voice. (The research also detects copies between different sources from wording and photos; the product does not yet.)
- **Two modes.** Until a model is trained, **starting assumptions** about each kind of source (field workers right 80 % of the time, public records 90 %, news 75 %, social media, video channels and other sources 60 %), with each vote weighted by the log-odds of its source being right and the sum read as log-odds. Once trained, a **model**: each source's own record on events with ground truth, shrunk towards its kind's record, with a calibration fitted on out-of-fold scores so that "80 %" means about 80 %.
- **Details.** Each supporting source's text is read for details (deaths, people affected, depth or fire size, cause; see [Details in report text](#details-in-report-text)). Per detail the suggestion shows every source's value and a best estimate (weighted by reliability: median for counts, most supported otherwise). Two credible sources stating values that disagree (counts beyond ±20 %, a different depth or cause; "cause unknown" disagrees with nothing) is a **detected dispute**.
- **Labels.** At least 80 %: verified, or partially verified when a detail is in dispute: marked wrong by an analyst on a credible source's link, or detected from the texts. At most 20 %: refuted. In between: conflicting when credible sources say both, otherwise unverified. No votes: insufficient evidence.
- **Endpoint:** `GET /api/v1/events/{id}/assessment-suggestion` (analyst, admin): label, probability, mode, the sources weighed most with their reliability and whether it was learned, details in dispute (and which were detected), and per detail every source's value with the estimate.
- **Training** (admin): `POST /api/v1/assessment/model/train`, or `python -m app.cli train-assessment`. It needs at least 10 events with ground truth and linked evidence, at least 3 that happened and 3 that did not. One event in five is held out first; the model, the starting assumptions and majority vote are scored on them (Brier score, accuracy) and stored with the model. The final model is then fitted on everything and becomes the only active one. `GET /api/v1/assessment/model` gives the status; `POST /api/v1/assessment/model/deactivate` goes back to the starting assumptions.
- **Analysts decide, and it is measured.** When an analyst changes an event's assessment, the suggestion at that moment (label, probability, mode, model, and whether it was followed) is written into the `event.updated` audit entry. The status counts how many assessments were set with a suggestion in view and how many followed it. The dataset export notes on each assessment label whether a suggestion was shown and followed, since a label made with a suggestion in view is not independent of it; the research scores suggestions against ground truth (`occurred`), not against analysts' labels.
- Migration 0010 adds `assessment_models` (reliabilities, calibration, held-out metrics; at most one active).

## Details in report text

The extraction module (`ai/extraction`) reads each field report's and signal's text for deaths, people or households affected, water depth or fire size, cause, the situation (over, getting worse, getting better, still going on) and denials, each with the words it came from. The backend uses a copy in `app/extraction`, so its image needs nothing outside `backend/`; `tests/test_extraction_copy.py` fails if the copy and the original differ (fix: `python backend/scripts/sync_extraction.py`).

- **Worked out when needed, not stored:** report text never changes, extraction takes milliseconds, and improved rules then apply to everything already collected.
- **API:** `details` on every field report and signal (`attribute`, `value`, `unit`, `surface`).
- **Assessment suggestions** compare the details across an event's sources (above).
- **Dataset export:** observation `claims` carry them, with `surface`; a denial sets `occurrence` to false; `language` comes from the same module. The manifest's `claims` note says which claims are automatic and not yet checked by annotators.
- `casualty_count` counts deaths, as the annotation guideline (0.3) now says.

## Copies among an event's evidence

Which linked items repeat an earlier item from another source, so a viral repost is one voice, not many (`app/services/copies.py`). This is the research's copy detector (`ai/fusion/carcux_fusion/dependence.py`) in the product, made stricter.

- **Detected** per event, against earlier items from other sources:
  - the same photo (difference hash within 6 bits);
  - the same words: character n-gram TF-IDF cosine **≥ 0.7** for news and other signals, **≥ 0.9** for field reports (field workers at the same spot write similar short sentences and are still two eyewitnesses);
  - attribution ("according to", "er moto", "এর মতে", "share korlam", "RT") with at least 0.3 of the text in common.

  Texts under 40 characters are never copies on wording alone, and an item that takes the opposite stance (quoting a claim to deny it) is not a copy. The type follows the dataset: `verbatim_copy` (the same words in order), `rewrite`, `cites`, `same_media`, `repost` (named by an analyst). The research used 0.6 on simulated text; these stricter values stay until real annotated copies can tune them.
- **Analysts decide:** `PUT /api/v1/events/{id}/evidence/{evidence_id}/copy` with `{"origin_evidence_id": …}` confirms a copy or names the origin; with `null` it says "not a copy"; `DELETE` goes back to the detection. Audit-logged (`event.copy_decided`). `GET …/evidence` shows each item's `copy_of` (origin, kind, reasons, detected / confirmed / rejected).
- **Counted once:** assessment suggestions and their training leave confirmed and detected copies out (the origin carries the voice); rejected ones count. The suggestion says how many items were counted once. (The research's proposed model keeps copies as a second, learned channel; the product drops them until there is enough real data to learn that weight.)
- **Dataset export:** copies become `dependences` with the right type and evidence; analyst-confirmed ones as that analyst's annotation (confidence 3, `annotator_judgement`), unreviewed detections as automatic (ANN-000, confidence 2); rejected ones are left out.
- Migration 0011 adds `copy_decisions` (one per linked item).

## Stance suggestions

How a report or signal bears on an event, suggested to the analyst who links it (`app/services/stance.py`). Transparent rules, each with its reason, strongest first:

1. **Contradicts** (strong): the text denies the event or calls it false or a rumour ("eta gujob", "খবরটি গুজব"), as the extraction module reads denials.
2. **Not this event** (medium): the item is about a kind of event in another family (its own type, or the type its words point to).
3. **Partly supports** (medium): it states a detail (deaths, people affected, depth, cause) that disagrees with the estimate from the event's other credible sources, with that detail as the conflict ("says 20 dead; other sources say 3 dead"). Copies are left out of the estimate.
4. **Related only** (weak): it asks or comments ("ki hoise?", "dua koren", "anyone know") and states nothing checkable.
5. **Supports** (weak) otherwise. The weakest suggestion: the analyst must read the item.

- **Where it shows:** candidate reports, signals and events (`stance` on each), each linked item on `GET /api/v1/events/{id}/evidence` (read without itself), and `POST /api/v1/events/{id}/stance` with `{"text": …, "event_type": …}` for text not yet in CARCUX (the add-link form).
- **A suggestion only.** The app marks the suggested option but never chooses it. When an analyst links an item or changes its relation, the suggestion at that moment and whether it was followed go into the audit log (`stance_suggested` on `event.evidence_linked` / `event.evidence_updated`).
- **Never in the blind queue:** `GET /api/v1/annotation/queue` carries no suggestion, so second opinions stay independent and agreement is not inflated.
- **How good is it:** `python -m app.cli evaluate-stance` compares the suggestions with blind second opinions (the fair test: made without seeing any suggestion) and with working labels (which may have seen it): accuracy, macro-F1 and F1 per relation, and how often analysts followed a suggestion. This is the rule baseline for stance in the CARCUX-BD dataset paper.

## Links pasted by analysts (Facebook, YouTube, news …)

Social media and any web page, without scraping (`app/services/links.py`, `services/signals.py`).

- **CARCUX never opens the link.** It reads the platform, the post's id and, where the address shows it, the account from the URL itself (Facebook posts, permalinks, `story.php`, shares, reels, groups, `fb.watch`; YouTube watch, `youtu.be`, shorts; X; TikTok; Instagram; Telegram; any website), and drops tracking parameters (`fbclid`, `utm_…`, `si` …). The analyst pastes what the post says. No logins, no crawling, and the server never fetches an address someone typed.
- **One source per account** (`Dhaka Updates · Facebook`), of kind `social` or `video_platform` (migration 0012), so each page or channel builds its own track record in assessment suggestions (starting assumption: right 60 % of the time). A website goes under its publisher: an existing feed's source when the domain matches, else a new one of the kind the analyst says.
- **One signal per post:** the same post pasted again, with any tracking, returns the existing signal (`created: false`).
- `GET /api/v1/signals/links/preview?url=…`: what the link is and whether it is already in CARCUX. `POST /api/v1/signals/links`: `url`, `account` (needed when the link does not show it), `text`, `published_at`, optional `event_type`, `district`, and `event_id` + `relation` to link it to an event at once. 201 when new.
- **Dataset export:** posts from `social` and `video_platform` sources are given by reference (the link) with their labels, `content_policy: reference_only`, no text, and claims without quoted words; videos have `modality: video`. Their sources are named only by platform ("Facebook account"), with `platform` and `account_ref`, a salted SHA-256 of the account (salt: `CARCUX_DATASET_SALT`, else derived from the JWT secret; set it once and keep it, so references stay stable across exports). With Docker, put it in `deployment/.env` (copy `deployment/.env.example`): Compose reads `.env` from the compose file's folder.

## Official pages

Verified accounts of government bodies and office holders (the Prime Minister's Office, ministries, departments, city corporations, district administrations, members of parliament, public agencies) that will publish statements about events (`app/models/official.py`, `app/services/official.py`). Migration 0013.

- **Admins only create and verify pages** (`POST /api/v1/official-pages`). A new page is *pending*: hidden from everyone but admins and its own officials.
- **Verification is a human check, recorded:** either *official email* (the office confirmed from its own address, stored on the page) or *official letter* (a PDF, JPEG or PNG scan up to 10 MB, checked by its bytes, stored under the media directory with its SHA-256; admins only can open it). `POST …/{id}/document`, then `POST …/{id}/verify` with the method and a note of what was checked (who confirmed, which address or letter reference, when). Who verified and when are kept on the page.
- **Suspend and reinstate** (`POST …/{id}/suspend` with a reason, `…/reinstate`): a suspended page is hidden again and cannot publish; reinstating returns it to verified (or pending, if it never was).
- **Official accounts** (`POST …/{id}/members`): a new role, `official`, for a named person at the office. The database refuses an official without a page, and a page for anyone else. Officials read the situation like viewers (map, events, signals) and see their own page; they do none of the analysts' work. On the Users page an official shows with its page; the role is given only from the page.
- **Reading:** `GET /api/v1/official-pages` (admins: all; others: verified), `GET …/by-slug/{slug}` (verified pages for everyone signed in; how it was verified and its officials only for admins and its own officials), `GET …/mine` for an official.
- Every step is audit-logged (`official_page.created`, `.updated`, `.document_added`, `.verified`, `.suspended`, `.reinstated`).

## Official statements

What a verified official page says about an event (`app/models/statement.py`, `app/services/statements.py`). Migration 0014.

- **Written from CARCUX's brief.** `GET /api/v1/events/{id}/brief` (officials of verified pages, analysts, admins) gives what CARCUX knows: the analysts' assessment, CARCUX's suggested assessment and how likely it is that the event happened, sources for and against (with how many are credible), disputed details with best estimates and the values stated, copies counted once, and each source's track record. **Field workers are never named** in a brief ("A field worker"); public sources are.
- **Publishing** (`POST /api/v1/statements`): only an active official of a *verified* page, not on a dismissed event. The official chooses a finding (*confirmed*, *partly confirmed*, *denied*, *under review*) and writes a title and the statement in their own words. The brief at that moment is stored with the statement, and the statement is marked `informed_by_carcux`.
- **Never ground truth for CARCUX.** A statement written from CARCUX's brief must not be used to evaluate CARCUX (that would be CARCUX grading itself). Ground truth stays with sources published independently afterwards.
- **Never edited or deleted** (a database trigger refuses both). A correction is a new statement with `supersedes_id`; one correction per statement, only by the same page on the same event, always of the latest. Readers see "corrected" with a link both ways.
- **Reading:** `GET /api/v1/statements` (filter `event_id`, `page_id`; newest first) and `GET /api/v1/statements/{id}` (with its brief), for everyone signed in, from verified pages only (admins and the page's own officials also see a suspended page's). Who wrote it is shown to admins and the page's officials only: the office speaks, not the person.
- Audit-logged (`statement.published`, with CARCUX's suggested label at the time).

## The public site: official posts, likes and comments

Official posts (statements of verified pages) are open to everyone at `/api/v1/public/...` (`app/api/public.py`, `app/services/public.py`). Migration 0015.

- **Reading, no account:** `GET /public/posts` (newest first), `/public/posts/{id}` (with visible comments), `/public/pages/{slug}`, `/public/incidents/{event_id}` (only once a verified page has posted about it). The public never sees the brief, the author or anything of the console. A suspended page's posts disappear.
- **Public accounts are separate from staff accounts** (`public_accounts`): their tokens are of another type, refused by staff endpoints (and staff tokens are refused here). Sign up with an email, a display name and a password (`POST /public/auth/signup`; the answer is the same whether the email exists, so it does not reveal accounts). An emailed link (48 h) confirms the address (`POST /public/auth/verify`); only then can the person sign in. The token itself is never stored, only its SHA-256.
- **Taking part:** like (`PUT`/`DELETE /public/posts/{id}/like`), comment (2 to 1000 characters, at most 5 per 10 minutes), report a comment (false information, abuse, spam, personal information, other), delete one's own comment. A comment reported by **3** different people is hidden at once until a moderator decides.
- **Moderation** (`/api/v1/moderation`): admins for every comment, officials for comments on their own page's posts. *Hide* (with a reason), *keep* (unhide; further reports no longer hide it). Admins *ban* an account (signed out, its comments hidden) and lift bans. All audit-logged.
- **Privacy:** stored are the email (never shown), the display name, a password hash, likes, comments and reports. `POST /public/auth/delete` with the password deletes the account and everything it posted. This is the only place CARCUX keeps profiles of the public.
- **Email:** without `CARCUX_SMTP_HOST`, emails are written to the backend log. The Docker stack sends them to Mailpit (inbox at http://localhost:8025). Settings: `CARCUX_SMTP_HOST`, `_PORT`, `_USER`, `_PASSWORD`, `_STARTTLS`, `CARCUX_MAIL_FROM`, `CARCUX_PUBLIC_BASE_URL` (for links), `CARCUX_PUBLIC_TOKEN_DAYS`.

## People's opinions on incidents

Once a verified page has posted about an event, its public incident page also carries **what people say** (`IncidentOpinion`, migration 0016).

- **Posting:** signed-in public accounts, `POST /api/v1/public/incidents/{event_id}/opinions` (2 to 1500 characters, at most 3 per 10 minutes). Shown at once with `GET /public/incidents/{id}` (`opinions`, newest first), marked as not verified. Report (`POST /public/opinions/{id}/report`): three reports hide it until a moderator decides; delete one's own (`DELETE /public/opinions/{id}`).
- **Moderation:** admins only (`/api/v1/moderation/opinions?state=reported|hidden|all`, `…/{id}/hide`, `…/{id}/restore`). Banning an account hides its opinions too.
- **Evidence for analysts:** each opinion is also a **signal**, from a source of its own per account ("<name> · CARCUX public site", type `social`, platform `carcux`), so every person builds a track record like any page. `GET /api/v1/events/{id}/public-opinions` (analysts) lists this incident's opinions not yet linked, with CARCUX's reading; they are kept out of "possibly related signals" so they are not listed twice. A hidden opinion's signal is dismissed (unless already linked); deleting an opinion or the account removes its words from the signal ("Removed by its author") and renames a deleted account's source.
- **Dataset:** as a social source, opinions are exported by reference with labels only, never their words, and the account only as its salted `account_ref`.

## Review, audit log and passwords

- **Review queue.** `GET /field-reports?status=submitted&order=oldest` lists what nobody has looked at, oldest first. Linking a report to an event, or `POST /field-reports/{id}/review`, takes it off the queue and records the reviewer and time; dismissing needs a reason.
- **Audit log.** `GET /api/v1/audit` (admin): newest first, filter by `action` (exact, or a prefix ending in `.` such as `event.`), `actor_id`, `target_type`, `target_id`, `since`/`until`. The response also lists every action name seen, for filter menus.
- **Passwords.** `POST /api/v1/auth/password` changes your own (current password required); it signs out your other sessions and returns a fresh token. `POST /api/v1/users/{id}/password` (admin) sets a temporary password and signs that person out everywhere. Both are audit-logged; passwords never are.
- **Rate limits** (`app/services/throttle.py`). They answer `429` with `Retry-After`:
  - **Sign-in, staff and public site:** 5 failures per email and address in 15 minutes, 20 per email in an hour, 30 per address in 15 minutes. Limits apply to unknown emails too, so a lock-out reveals nothing. A locked account is refused even with the right password, which is what stops guessing. A successful sign-in clears that email and address's failures.
  - **Current-password checks** (change password, delete public account): 5 in 15 minutes.
  - **Public sign-ups:** 5 per address and 3 per email an hour.
  - **Field reports:** 60 per worker in 10 minutes.

  Counts are keyed by a keyed hash of the email, never the email itself, and rows are kept for a day. Refused sign-ins are audit-logged as `auth.login_throttled`.
- **Client addresses.** The frontend passes the browser's address in `X-Forwarded-For`. It is believed only from private and loopback addresses (`CARCUX_TRUST_FORWARDED_FROM_PRIVATE`, default true). Without a reverse proxy that overwrites the header, a browser can claim any address. In that case only the per-email limits hold, and audit-log addresses are what the browser claimed. Put nginx or Caddy in front for production (deployment hardening).

## Overview

`GET /api/v1/overview` (everyone signed in) feeds the console's status bar: open events by priority and reports observed in the last 24 hours (a field worker's own). Analysts and admins also get flagged reports in the last 24 hours and the number of reports nobody has reviewed yet; for others those are `null`.

## Audit log

Logins (success and failure), account creation and changes, field report submissions and verifications, every event and evidence change, signal entry and triage, and source changes are written to `audit_log`. The table is **append-only**: a database trigger rejects every UPDATE and DELETE.

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
│   ├── cli.py           # command-line tasks (create-admin, ingest, export-dataset)
│   ├── ingest/          # source adapters, keyword classifier, gazetteer, runner
│   ├── extraction/      # copy of ai/extraction (details, language, places, times) and its gazetteer
│   ├── core/            # settings, password hashing, tokens
│   ├── db/              # base model, engine and sessions
│   ├── models/          # database tables
│   ├── schemas/         # request and response models
│   ├── services/        # business logic shared by API and CLI
│   └── api/             # routers and dependencies
├── migrations/          # Alembic migrations
└── tests/
```
