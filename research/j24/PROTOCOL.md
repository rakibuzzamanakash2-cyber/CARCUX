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
   restated as claims.

Fact-checkers are ground truth, so they are never also sources in the model.

## Units and labels

- **Claim** (dataset `event`): one neutral, checkable statement: what, where, when.
  Types: occurrence, count, attribution, media authenticity, official action. Event types
  are schema v1.3's `civil_unrest` and `information` families.
- **Item** (dataset `observation`): one report about a claim by one source, with time and
  language. **Stance** (dataset `relation`): supports, partially supports, contradicts,
  related, unrelated; two annotators, blind to each other and to the verdict; Cohen's κ;
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
docker run --rm -v "${PWD}:/repo:ro" -v "D:\CARCUX-J24:/out" -e CARCUX_J24_SALT `
  -e PYTHONPATH=/repo/data/tools -e PYTHONDONTWRITEBYTECODE=1 python:3.12-slim `
  sh -c "pip install -q --root-user-action=ignore jsonschema openpyxl && python -m carcux_data.j24 index --out /out && python -m carcux_data.j24 recurrence --out /out && python -m carcux_data.j24 claim-sheet --out /out"
```

The salt must be the same in every later run, or social links will hash differently. A
salt that has been shown in a chat or a screenshot is no longer private: make a new one
and index again.

## Changes

- 17 October 2026: the Docker command runs the tool from the read-only source folder
  (no install into the repository, which Windows refused) and keeps the salt in a file.
  Procedure only; nothing in the design changed.
