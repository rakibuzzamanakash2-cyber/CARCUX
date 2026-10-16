# 1 · Extraction: Bangla / Banglish / English

**Role:** engineered with existing methods · **Spec:** §6, §9.2 · **Status:** language identification, detail extraction (counts, depth, cause, status, denials), place names with coordinates, and time expressions made absolute, all as transparent rules, all in the product; checked on hand-written examples (development and held-out) and simulated data. Evaluation on analysts' real labels and an LLM extractor baseline are next.

Turns raw text (field reports, news excerpts, posts) into structured observations: the details that fusion compares across reports (RQ3) and the dataset records.

## In → out

| In | Out (schema v1) |
|---|---|
| Raw text | `observation.language` (`bn` / `bn-Latn` / `en` / `mixed`) |
| | `observation.claims`: occurrence (when denied), casualty_count, affected_count, magnitude, cause, status, each with the words it came from (`surface`) |
| Raw text + gazetteer | `observation.location_mentions`: places the text names, with coordinates and precision |
| Raw text + publication time | `observation.observed_at`: the earliest clear time the text gives, in Bangladesh time |

```python
from carcux_extraction import detect_language, extract

extract("Mirpur 10 e hatu pani, 3 jon mara geche bhari brishtir karone")
# casualty_count 3 (deaths), magnitude knee-deep, cause heavy rain
detect_language("টানা বৃষ্টিতে হাঁটুসমান পানি")  # "bn"
```

Standard library only, so the backend can use it as it is.

## What it extracts

| Attribute | From | Examples |
|---|---|---|
| `occurrence` = false | a denial or "rumour" | "the report is a rumour", "খবরটি গুজব", "kono agun lage nai" |
| `casualty_count` (deaths) | a number and a death word; "no casualties" gives 0 | "3 killed", "তিনজন নিহত", "2 jon mara geche", "death toll rises to 12" |
| `affected_count` (people or households) | a number, who, and affected / stranded / marooned / displaced / in shelters | "1.5 lakh people marooned", "৫০০ পরিবার পানিবন্দী", "300 poribar pani bondi" |
| `magnitude` | water depth on the guideline's scale; fire size | "knee-deep", "হাঁটুসমান পানি", "komor pani"; "massive fire", "ভয়াবহ আগুন" |
| `cause` | a short normalised phrase | heavy rain, river overflow, embankment breach, upstream runoff, blocked drains, electrical short circuit, gas leak, cylinder explosion, vehicle collision, protest, maintenance work, unknown |
| `status` | resolved, worsening, improving, ongoing | "water has receded", "পানি বাড়ছে", "pani komche", "still" |

Design choices:

- **Precision first.** A detail is taken only when the wording is clear. Vague amounts ("hundreds", "কয়েকশ", "koyekjon") give no number; injuries are not deaths (the guideline's `casualty_count` counts deaths); a count never reaches across a clause ("একজন নিহত, তিনজন আহত" is one death).
- **Causes that could be the event itself need a causal cue.** "Heavy rain continues" reports rain, not a cause; "after heavy rain", "টানা বৃষ্টিতে", "brishtir karone" give one.
- **Numbers as people write them:** 1,250 · ১২৫০ · 12,50,000 · 1.5 lakh · দেড় লাখ · tin hajar · two dozen.
- **One Unicode form for Bangla** (য়, ড়, ঢ় precomposed or with a nukta read the same).
- **Explainable:** every claim carries the words it came from.

## Places (`places.py`)

The gazetteer (`data/bd_gazetteer.json`, built by `scripts/build_gazetteer.py` from nuhil/bangladesh-geocode, MIT) has 8 divisions, 64 districts, 481 upazilas and 48 city localities (approximate centres, within about 2 km). Names are matched as people write them:

- English, Bangla and older spellings: Chittagong → Chattogram, Comilla → Cumilla;
- Bangla case endings: ঢাকায়, ফেনীর, মিরপুরে;
- Banglish endings attached or hyphenated: Mirpure, Mirpur-e, Dhakay, Feni-te, Fenir; and the English possessive (Old Dhaka's);
- the longest name first: "Mirpur 10" and "Old Dhaka" win over "Mirpur" and "Dhaka".

**Ambiguous names are settled by the text.** Mirpur is a Dhaka locality and an upazila of Kushtia; Lohagara, Kaliganj, Kachua and six other names are upazilas in more than one district. A candidate in a district the text also names wins ("Kushtia-r Mirpur upazilay" → Kushtia); otherwise the most specific level. Upazilas sit at their district's centre (the source has no upazila coordinates), so their precision is district-wide (30 km). Names that are also districts, or shorter than five letters, are left out of the upazila list, as the original build did; names shared by several upazilas are now kept, because the text settles them.

`best_place()` gives the place an item is about (the first place, refined to the most specific in the same district, widened when the text names several districts), which is how news items are put on the map.

## Times (`times.py`)

Time expressions are made absolute against the publication time, in Bangladesh time (UTC+6):

| Kind | Examples | Result |
|---|---|---|
| Day words | today, yesterday, last night, আজ, গতকাল, গত রাতে, ajke, gotokal | the day (last night runs to 06:00) |
| Part of the day with a day word | আজ সকালে, gotokal sondhay, this morning | a window: dawn 04–06, morning 06–12, noon 12–15, afternoon 15–18, evening 18–20, night 20–24 |
| Clock times | at 9:50pm, 10.30 am, রাত ১০টায়, raat 10 tay, sokal 9 tar dike, ১০টা ৩৮ মিনিটে | the minute; "raat 10" is 22:00, "rat 2" 02:00; a bare clock time later than publication is the day before |
| Dates | 29 February, Nov 21, ২১ নভেম্বর, 21 November 2025 | the day; a date later than publication without a year is last year's |

Combinations are read together ("at 9:50pm on 29 February", "গতকাল রাত ১০টায়"). Precision first: "kal" / "কাল" alone (yesterday or tomorrow) and a part of the day with no day word ("Shondhay …") are left out. `observed_at()` is the earliest clear time not after publication.

## Run it

From `ai/extraction` (Python 3.12):

```bash
pip install -e ".[dev]"
python -m carcux_extraction.evaluate                 # the development examples
python -m carcux_extraction.evaluate --held-out      # examples the rules were not tuned on
python -m carcux_extraction.evaluate DATASET_DIR --misses 20 --json out.json   # a CARCUX-BD export
python -m carcux_extraction.evaluate_where_when              # places and times, development
python -m carcux_extraction.evaluate_where_when --held-out   # places and times, held out
python scripts/build_gazetteer.py <dir with districts.json, divisions.json, upazilas.json>
pytest -q && ruff check . && ruff format --check .
```

Scores per attribute (precision, recall, F1), with values agreeing as in the guideline (§5.2): counts within ±20 %, everything else exactly.

## Results so far (not on real labels yet)

| Set | Examples | Macro precision | Macro recall | Macro F1 | Language |
|---|---|---|---|---|---|
| Development (written with the rules) | 51 | 1.000 | 0.986 | 0.992 | 1.000 |
| **Held out, first run** | 38 | **0.972** | **0.799** | **0.877** | 0.974 |
| Held out, after one bug fix | 38 | 1.000 | 0.823 | 0.902 | 0.974 |

- **Development examples** (`carcux_extraction/data/dev.jsonl`): written by hand alongside the rules, in all three languages, including hard cases. They show what the rules cover, not how well they generalise.
- **Held-out examples** (`held_out.jsonl`): written by the same author after the rules, run once, with different phrasings. The first run is the honest figure. It found one real bug: a death count reaching across a comma into the injured count ("একজন নিহত, তিনজন আহত" gave 3). That bug was fixed, so the set is no longer clean; no other rule was changed for it. Remaining misses, kept as known gaps: "lightning strikes kill 11" (verb before the number), "the river breached the embankment", "spread to adjacent buildings" (worsening), "komor porjonto" without the word for water, "1 hajar er beshi poribar" (a word between number and noun), and an English word inside Bangla script ("news টা fake").
- **Simulated CARCUX-BD** (1,120 observations, generator 0.2): deaths, numbers affected and denials are near perfect; magnitude recall is low by design (the simulator writes bare "minor", "large", which are not clear enough to take), and most cause and depth "false positives" are the simulator contradicting itself (its base sentence says "flooded after the downpour" or "knee-deep", then appends a different labelled cause or depth). Fusion reads the simulator's labelled details, not the text, so the fusion results are unaffected.

### Places and times (16–17 October 2026)

| Set | Examples | Places P / R / F1 | Times P / R / F1 |
|---|---|---|---|
| Development (written with the rules) | 30 | 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 |
| **Held out, first run** | 30 | **1.000 / 0.923 / 0.960** | **1.000 / 0.929 / 0.963** |
| Held out, after two fixes | 30 | 1.000 / 1.000 / 1.000 | 1.000 / 0.929 / 0.963 |

A place counts as found when its name and district match; a time when its start (to the minute) and precision match. The first held-out run found two gaps, which were fixed: the English possessive ("Old Dhaka's Lalbagh") and the spelling "Shahbag". The third miss, a part of the day with no day word ("Shondhay Bailey Road e agun"), is kept as a known gap, because such a word alone does not say which day. Nothing was wrong, only missed: precision stayed at 1.000.

**Caveats.** All examples were written by one person who also wrote the rules; real reports will be messier (spelling, abbreviations, code-mixing). The number to report is the score on analysts' claims in a real CARCUX-BD export, which comes with the real-data sprint.

## Next

1. ~~Into the product~~: done. Reports and signals show their details, the dataset export carries them as claims, and assessment suggestions detect disputed details from them (`backend/app/extraction` is a checked copy; see the backend README). Places put news items on the map and go into the export as `location_mentions` (field reports: GPS and the places their text names); signals' `observed_at` comes from their text.
2. **Evaluate on real labels** from the data sprint; extend the rules where real reports differ.
3. **An LLM extractor as a strong baseline** (local model through Ollama, as in fusion's B6).
4. ~~Place names and time expressions~~: done (above). Next for places: upazila coordinates (centroids from a boundary file), and street-level places from OpenStreetMap for Dhaka and Chattogram.
