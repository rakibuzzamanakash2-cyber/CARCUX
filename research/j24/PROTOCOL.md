# CARCUX-J24 protocol

A multi-source claim dataset from Bangladesh's July–August 2024 uprising, and a
pre-registered test of CARCUX's fusion on it. Version 0.1, frozen on 17 October 2026 at
the commit that adds this file; any later change is listed under *Changes* with its date
and reason, before the test set is looked at.

The feasibility check behind it is the document *CARCUX-J24 feasibility and protocol
v0.1* (17 October 2026).

## Ethics statement

**Purpose.** Research and education: a dataset for studying how reports about a crisis
agree, disagree and copy one another, and a test of methods that weigh sources by how
reliable they have been. Not journalism, not advocacy, and not a judgement of any
person, party or side.

**What is studied.** Claims about events (something happened, somewhere, at some time)
and what organisations published about them: newspapers, broadcasters, news agencies,
official bodies and fact-checkers. Their public reporting is the object of study, so
organisations are named.

**What is never collected or stored.**
- Names, photographs or contact details of victims, witnesses or any private individual.
  Claims are written without them ("a student", "a man").
- Social media handles. An account appears only as a salted hash, so the same account can
  be recognised without saying who it is.
- Copies of posts, articles, photos or videos. The dataset holds links, dates, short
  excerpts (at most 300 characters, with names replaced by [PERSON]) and labels.
- Any political attribute of anyone: no party, side, ideology or religion is recorded
  for a person or an outlet (CARCUX scope boundary). The country where an outlet is
  registered is recorded, as a fact, and used only in the pre-registered analysis H4,
  never by a model.

**Truth is not ours to decide.** Whether a claim is true comes only from independent
professional sources: the UN human rights office's fact-finding report and the published
verdicts of recognised fact-checking organisations. Nobody on this project labels a claim
true or false. Annotators label only what each report says about a claim (its stance).

**Even-handedness.** Claims enter the dataset through two fixed rules (every claim checked
by the listed fact-checkers in the window; every incident the UN report finds), not by
choice. Claims about every side and every period, including violence after 5 August 2024,
are included as the fact-checkers and the UN found them. Whether Bangladeshi or foreign
outlets were more accurate is tested in both directions; no outlet is assumed reliable or
unreliable.

**Harm.** Social media links, which can lead to private individuals, are kept in a
separate restricted folder and are never published; researchers may request them under a
data-use agreement. Annotators use pseudonyms, are warned that material describes deaths
and violence, may skip any item and are never required to watch videos. Anyone may ask for
an item to be removed (takedown address in the dataset card).

**Collection.** Only public pages, through public interfaces, at one request every two
seconds or slower, honouring robots.txt, with an identifying user agent. Fact-check
articles and news pages are read, not republished.

**Approval.** The supervisor is informed of the project. Journals ask for an ethics
statement; this section is it, and a statement from the university's ethics committee
(approval or exemption) is added here before submission.

## Window

1 July – 15 August 2024 (the period of the OHCHR report).

## Sampling frames

1. **Fact-check frame:** every fact-check published in the window by Rumor Scanner,
   Dismislab, FactWatch, BD FactCheck (indexed automatically, `carcux_data.j24`),
   AFP Fact Check Bangla and BOOM Bangladesh (indexed by hand), about an event of the
   uprising or its aftermath.
2. **Incident frame:** every incident the OHCHR report finds on reasonable grounds,
   restated as claims. Coding: incidents only (violence, arson, shutdowns, curfews, arrests,
   public official actions and statements), not the report's findings on orders or
   responsibility; no names of victims or private people; no party, side or religion of any
   person; individual accounts of sexual violence and torture left out (no date or place to
   match, and restating them adds harm). A claim the report finds true or false is tier A; a
   claim it cannot confirm is unresolved; a figure or allegation it only passes on from
   another source (police, ministry, media) is kept for matching but is not ground truth.
   Claims are drafted from the report's text, each with its paragraph, page and a verbatim
   excerpt checked by program, and every one is checked by a person before use.

Fact-checkers are ground truth, so they are never also sources in the model.

## Items: what outlets published

Fact-checks cite few outlets each (median 1 in the pilot), so the reports about each claim
are collected from the outlets themselves:

- **Outlets:** every outlet cited by 3 or more fact-checks in the pilot index, plus BBC
  (English and Bangla), Al Jazeera, Reuters, AP, AFP, DW, The Guardian and The New York
  Times. The list is fixed in `carcux_data/j24/news_outlets.csv` before collection.
- **As published at the time:** articles are listed from the outlets' own sitemaps (or,
  for an outlet without usable sitemaps, the Internet Archive's index), and each is read
  from the Internet Archive (Wayback Machine) copy captured nearest to its published date,
  so later edits and deletions do not change what an outlet is recorded as having said. The
  capture time is stored with the item; a copy captured more than 30 days after the window
  is flagged, and an article with no copy in the archive is counted, not read live.
- **Stored:** link, outlet, capture time, published time when the page states it, title
  and an excerpt of at most 300 characters. Full text stays only in the collector's local
  cache, used to suggest which claims an article is about, and is never published.
- **Matching and stance:** the collector suggests article–claim pairs (place, date, topic
  words); people decide whether each pair is about the claim and label its stance. Nothing
  is labelled automatically.
- Gaps are reported, not filled: the internet shutdown (18–23 July) and outlets with few
  captures will have fewer items.

## Units and labels

- **Claim** (dataset `event`): one neutral, checkable statement: what, where, when.
  Types: occurrence, count, attribution, media authenticity, official action. Event types
  are schema v1.3's `civil_unrest` and `information` families.
- **Item** (dataset `observation`): one report about a claim by one source, with time and
  language. **Stance** (dataset `relation`): supports, partially supports, contradicts,
  related, unrelated; two annotators, blind to each other and to the verdict; Cohen's κ;
  "partially supports" means the item says the event happened but states a detail
  (number, place, date, cause) differently from the claim (not from the ground truth, which
  annotators do not see), as in the one-page annotator instructions v1.0;
  disagreements adjudicated. **Copies** (dataset `dependence`) as in CARCUX-BD.
- **Ground truth tiers:** A, a finding of the OHCHR report; B, a fact-check resting on
  primary evidence; C, two or more fact-checkers agreeing on secondary evidence.
  Unresolved claims are kept and excluded from veracity scores.

## Pilot (go / no-go)

1. Index the fact-checks (`python -m carcux_data.j24 index`).
2. Count recurring sources (`recurrence`).
3. Restate claims and confirm verdicts in the claim sheet (`claim-sheet`, `check-sheet`).
4. Restate the OHCHR incidents as claims.
5. Stance pilot: 50 items, two annotators.

Go if: at least 250 resolved claims; at least 25 % true after adding the incident frame;
at least 20 sources each on 5 or more claims. Otherwise the indexed fact-checks become a
smaller supplementary test in Paper 1.

## Evaluation (pre-registered)

- **Split:** claims grouped by incident; 70 / 30 by group, stratified by frame and phase;
  the test set drawn once with a seed fixed in this file before drawing, sealed, used once.
  Secondary: temporal (train July, test August).
- **Methods:** majority vote, TruthFinder, B7 social sensing (variants), a language-model
  judge, CARCUX `reliability-dep`; as implemented in `ai/fusion` at the frozen commit.
- **Metrics:** Brier score (primary), ECE, AUROC, share of false claims marked verified at
  80 %; paired bootstrap; results by frame and overall, calibration checked within frame.
- **Fact-checker robustness:** about two-thirds of the pilot's fact-checks are Rumor
  Scanner's, so results are also reported by fact-checker, and the primary analysis is
  repeated without Rumor Scanner's claims. Claims checked by more than one fact-checker
  report their agreement; a disagreement makes the claim unresolved.
- **H1** (descriptive): sources recur across claims.
- **H2** (primary): on the test set, `reliability-dep` has a lower Brier score than B7 and
  majority vote.
- **H3** (exploratory): source reliability differs between phases (to 18 July; the
  shutdown, 18–23 July; 24 July–4 August; after 5 August). Direction not assumed.
- **H4** (exploratory): reliability differs between outlets registered in Bangladesh and
  elsewhere. Either direction, or none, is reported as found.

Split seed: to be fixed here before the split is drawn.

## Running the pilot on Windows (Docker)

From `D:\CARCUX` in PowerShell. The output goes to `D:\CARCUX-J24`, outside the
repository, so nothing collected can be committed by mistake.

```powershell
# Once: make a private salt for hashing social media links and save it to a file.
# It is never printed. Keep the file (back it up); never paste its contents anywhere.
([guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")) |
  Set-Content -NoNewline D:\CARCUX-J24-salt.txt

# Each run (the repository is mounted read-only; output goes to D:\CARCUX-J24):
$env:CARCUX_J24_SALT = Get-Content -Raw D:\CARCUX-J24-salt.txt
docker run --rm -e PYTHONUNBUFFERED=1 -v "${PWD}:/repo:ro" -v "D:\CARCUX-J24:/out" -e CARCUX_J24_SALT `
  -e PYTHONPATH=/repo/data/tools -e PYTHONDONTWRITEBYTECODE=1 python:3.12-slim `
  sh -c "pip install -q --root-user-action=ignore jsonschema openpyxl && python -m carcux_data.j24 index --out /out && python -m carcux_data.j24 recurrence --out /out && python -m carcux_data.j24 claim-sheet --out /out"
```

### Claim sheet in batches (for a helper)

The claim sheet can be split into files of about 25 fact-checks, each with a bilingual
"Start here" page, a progress counter, clickable links and a `maybe_same_as` hint for rows
whose titles look like the same claim (a hint only; the person decides). Work already in
the sheet is carried over. The helper gets one batch at a time and enters a pseudonym in
`checked_by`. Whoever fills the claim sheet sees the fact-checkers' verdicts, so they are
not a stance annotator for J24.

```powershell
# Split D:\CARCUX-J24\claim_sheet.xlsx into D:\CARCUX-J24\batches\batch_01.xlsx, …
docker run --rm -v "${PWD}:/repo:ro" -v "D:\CARCUX-J24:/out" -e PYTHONPATH=/repo/data/tools `
  -e PYTHONDONTWRITEBYTECODE=1 python:3.12-slim `
  sh -c "pip install -q --root-user-action=ignore openpyxl && python -m carcux_data.j24 split-sheet --out /out --checked-by annotator-C"
# When the batches come back (saved into the same folder): join and check them
docker run --rm -v "${PWD}:/repo:ro" -v "D:\CARCUX-J24:/out" -e PYTHONPATH=/repo/data/tools `
  -e PYTHONDONTWRITEBYTECODE=1 python:3.12-slim `
  sh -c "pip install -q --root-user-action=ignore openpyxl && python -m carcux_data.j24 merge-sheets --out /out"
```

### News collection

Stage 1 lists each outlet's articles in the window from its sitemaps (outlets in
parallel). Stage 2 reads them from the archive, one request every 4 seconds, articles whose
title names the uprising first. A stopped run resumes where it stopped. An outlet whose
sitemaps give nothing can be listed with `news-list --from archive --outlets KEY` (slow).

```powershell
# Stage 1: list (all outlets)
docker run --rm -e PYTHONUNBUFFERED=1 -v "${PWD}:/repo:ro" -v "D:\CARCUX-J24:/out" -e PYTHONPATH=/repo/data/tools `
  -e PYTHONDONTWRITEBYTECODE=1 python:3.12-slim `
  sh -c "pip install -q --root-user-action=ignore jsonschema openpyxl && python -m carcux_data.j24 news-list --out /out"
# Stage 2, trial: one day, three outlets
docker run --rm -e PYTHONUNBUFFERED=1 -v "${PWD}:/repo:ro" -v "D:\CARCUX-J24:/out" -e PYTHONPATH=/repo/data/tools `
  -e PYTHONDONTWRITEBYTECODE=1 python:3.12-slim `
  sh -c "pip install -q --root-user-action=ignore jsonschema openpyxl && python -m carcux_data.j24 news-fetch --out /out --outlets prothomalo,thedailystar,bbc --since 2024-07-18 --until 2024-07-18"
```

The salt must be the same in every later run, or social links will hash differently. A
salt that has been shown in a chat or a screenshot is no longer private: make a new one
and index again.

## Changes

- 28 October 2026, before any article is labelled and before any result: the matcher.
  `news-texts` writes the text of every collected article that is an article, has at
  least 300 characters of text and was published in the window (or has no known date),
  from the saved pages. `claims-match` then ranks candidate articles for each claim group
  of claims v1: articles dated from 7 days before to 21 days after the claim's date (its
  event date, else a week before the first fact-check), ranked by BM25 on words with a
  light Bangla suffix strip; the query joins the English claim with the fact-checkers' own
  Bangla titles and sentences, so Bangla articles are found without translation. With
  `--embed`, BM25 is fused (reciprocal rank fusion, k = 60) with the multilingual
  sentence model intfloat/multilingual-e5-small. The top 10 per group go to a candidate
  sheet for stance labelling (repeats, questions, corrects, mentions, unrelated). The
  sheet shows no verdicts; annotator-A has seen the verdicts and does not label stance.
  These settings (window, top 10, model) are fixed before labelling and not tuned on
  labelled pairs.

- 28 October 2026, before the matcher is built and before any result: the fact-check
  claim sheet is complete. All 459 fact-checks (Rumor Scanner, Dismislab, FactWatch,
  1 July–15 August 2024) were drafted by an AI assistant and checked row by row by
  annotator-A; 290 are about the uprising. Rules settled while checking: (1) the check
  says whether the draft is right, never whether the news is true; an annotator's own
  view of what happened is not recorded, and a row the annotator disagrees with is marked
  "disputed" with the fact-checker's verdict kept; (2) a fact-check that covers several
  claims at once (a roundup) is coded misleading as a whole, with one general claim;
  (3) a fact-check of a claim already in the sheet (another fact-checker, or an English
  version) points to it with same_claim_as and keeps its own fact-checker's verdict, so
  disagreements between fact-checkers stay visible; (4) satire is not a verdict, and a
  satire row is dropped; (5) a live-update page is not a fact-check and is dropped. A
  consistency pass (codes, links, dates, privacy) fixed two event codes and removed
  remaining names, religion and party labels attached to persons from the evidence text.
  Merged with the 107 OHCHR incident claims into claims v1: 397 rows in scope in 323
  claim groups, 96 of them ground truth (OHCHR found or contradicted). Because annotator-A
  marked nearly every draft as correct, a random sample of 100 fact-check rows (seed 2024)
  will be fully re-checked against the source and the draft error rate reported.

- 28 October 2026, before any article is matched to a claim and before any result: the
  article reader was fixed on 18 saved sample pages from six outlets. Dates are now read
  in the formats the outlets use (Bangla digits and month names, "29 June 2024", "2024-07-18
  10:05"), and a placeholder date (1970) or one without a day is rejected. When the page's
  own date field is missing or unusable, the date is taken, in this order, from the
  article's address (Kaler Kantho, Somoy), the line after "প্রকাশ:" or "Published:", a
  time stamp in the page's script data, and last the upload time in the lead image's file
  name (Jugantor prints no article date; this is an approximation). Each record says where
  its date came from (`published_source`), so the approximate ones can be left out of any
  analysis that depends on time. Ittefaq captures were saved still compressed and are now
  decompressed (its earlier "text" was unreadable bytes); Somoy's text is read from its Nuxt
  page state; Kaler Kantho's escaped JSON-LD body is cleaned. Section pages (for example
  /country-news) are marked `is_article: false`. Some Kaler Kantho captures are empty
  page shells and have no text to recover.

- 28 October 2026, before any claim from the fact-check frame is used and before any
  result: the claim sheet is drafted by an AI assistant from each fact-check's own text
  (exported from the local cache, `factcheck-export`) and every row is then verified by a
  human annotator against the fact-check (ok / fix / drop), as was done for the OHCHR
  incident claims. The verdict is the fact-checker's, copied from its article, never the
  assistant's or the annotator's own judgement. Drafted and verified rows are reported as
  such. Reason: the helper annotator could not take part.

- 28 October 2026, after collection and before any matching, stance label or result: the
  article reader also takes text from a page's JSON-LD article body, its script data, or
  its longer text blocks when the page has no paragraphs (BBC, Ittefaq and Kaler Kantho
  pages had yielded no text), and all collected pages are re-read offline from the cache
  with it (`news-rebuild`), joining the parallel runs and dropping duplicates. Articles are
  later kept for matching only if published in the window. Coverage notes: most Desh
  Rupantor articles listed by its sitemaps have no archive copy (about 7,000), and many
  Hindustan Times copies failed; both are reported per outlet.

- 24 October 2026, before any stance label or result: outlet address filters are matched
  against the decoded address (Bangla-script addresses are stored percent-encoded, so DW
  Bangla matched nothing), and DW Bangla is kept whole, as it reports mostly on Bangladesh.
  The Guardian's archive index refused access (HTTP 403) twice; it is a coverage gap.

- 18 October 2026, before any stance label or result: the archive index is read page by
  page (its paged interface, `news-list --from archive-pages`), because week-by-week prefix
  queries made the index search each section's whole history and time out (HTTP 503/504).
  Same index, same window and filters; procedure only.

- 18 October 2026, before any stance label or result: a probe of the 30 outlets without
  usable sitemaps found a working date-listing page for 1 (5 block automated requests with
  403, Reuters disallows robots, several build their pages with JavaScript, the rest use
  addresses the probe did not guess). GDELT's public article index, checked for 2 August
  2024, listed no articles for most Bangladeshi outlets and 10–19 % of the sitemap-listed
  articles of the two it did list, so it is not used. Missing outlets are listed from the
  Internet Archive's index (slow, unattended) in a fixed priority order; outlets still
  unlisted when collection closes are reported as coverage gaps.

- 18 October 2026, before any claim was used or any result: coding rules for the incident
  frame added (see Sampling frames), after reading the OHCHR report and before checking the
  draft claims.

- 18 October 2026, before any claim was restated: the claim sheet may be filled in batches
  by a second person (pseudonym in `checked_by`), with a tool hint for possible duplicates
  that the person confirms or ignores. Who filled each row is kept. The claim sheet's
  filler is excluded from stance annotation, since they have seen the verdicts. Procedure
  only.
- 18 October 2026, before any claim, stance or result: reading order uses the listed title,
  or a headline-like address, to read likely-uprising articles first; a first pass may skip
  articles whose title or address is clearly about something else (`--only-likely`), and a
  second pass reads them, or the number left unread is reported per outlet. Sitemaps listed
  12 of the 42 outlets; the rest are listed from the archive index, more slowly, and any
  outlet still unlisted is reported as a coverage gap.
- 18 October 2026, before any stance label: "partially supports" is judged against the
  claim's own details, so annotators stay blind to the verdict (CARCUX-BD judges it against
  ground truth, which J24 annotators must not see).
- 18 October 2026, before any claim, stance or result: articles are listed from outlets'
  sitemaps instead of the Internet Archive's index, which in the trial (three outlets)
  answered with repeated 503 and 504 errors over ten hours and left whole weeks unlisted;
  articles are still read from archive copies (1,306 read in the trial, none failed).
  Copies captured more than 30 days after the window are flagged. Procedure only.
- 17 October 2026, after the pilot index and before any claim, stance or result:
  added the item collection from outlets (Wayback captures, fixed outlet list) and the
  fact-checker robustness analyses, because the pilot found a median of one outlet per
  fact-check and two-thirds of fact-checks from one organisation.
- 17 October 2026: the Docker command runs the tool from the read-only source folder
  (no install into the repository, which Windows refused) and keeps the salt in a file.
  Procedure only; nothing in the design changed.
