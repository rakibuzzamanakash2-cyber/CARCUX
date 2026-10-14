# 1 · Extraction: Bangla / Banglish / English

**Role:** engineered with existing methods · **Spec:** §6, §9.2 · **Status:** language identification and detail extraction (counts, depth, cause, status, denials) built, as transparent rules; checked on hand-written examples and simulated data. Place names and time normalisation, an LLM extractor baseline, and evaluation on analysts' real labels are next.

Turns raw text (field reports, news excerpts, posts) into structured observations: the details that fusion compares across reports (RQ3) and the dataset records.

## In → out

| In | Out (schema v1) |
|---|---|
| Raw text | `observation.language` (`bn` / `bn-Latn` / `en` / `mixed`) |
| | `observation.claims`: occurrence (when denied), casualty_count, affected_count, magnitude, cause, status, each with the words it came from (`surface`) |
| | *later:* `location_mentions` (geocoding), times normalised to ISO 8601 |

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

## Run it

From `ai/extraction` (Python 3.12):

```bash
pip install -e ".[dev]"
python -m carcux_extraction.evaluate                 # the development examples
python -m carcux_extraction.evaluate --held-out      # examples the rules were not tuned on
python -m carcux_extraction.evaluate DATASET_DIR --misses 20 --json out.json   # a CARCUX-BD export
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

**Caveats.** All examples were written by one person who also wrote the rules; real reports will be messier (spelling, abbreviations, code-mixing). The number to report is the score on analysts' claims in a real CARCUX-BD export, which comes with the real-data sprint.

## Next

1. ~~Into the product~~: done. Reports and signals show their details, the dataset export carries them as claims, and assessment suggestions detect disputed details from them (`backend/app/extraction` is a checked copy; see the backend README).
2. **Evaluate on real labels** from the data sprint; extend the rules where real reports differ.
3. **An LLM extractor as a strong baseline** (local model through Ollama, as in fusion's B6).
4. **Place names and geocoding** against the Bangladesh gazetteer; **time normalisation** ("ajke shokale", "gotokal raat theke").
