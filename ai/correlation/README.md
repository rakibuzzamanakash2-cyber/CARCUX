# 4 · Correlation: which observations describe the same event?

**Role:** ⭐ **research core (Q1 paper)** · **Spec:** §5.1 (RQ1), §7.2 · **Status:** evaluation harness, baselines and first joint model done; checked on simulated data only, real labelled data still needed

Groups a stream of observations into real-world events using **meaning, place and time together**, and links child events to parents (a road blockage caused by waterlogging).

## In → out

| In | Out (schema v1) |
|---|---|
| Observations with claims, `location_mentions`, `published_at` / `observed_at` | Event clusters: observation → `event_id` |
| | `parent_event_id` links |
| | `unrelated` decisions (hard negatives rejected) |

## Research question

**RQ1:** Does jointly modelling semantic, spatial and temporal similarity improve event correlation compared with semantic similarity alone?

## Method (what is built)

| Part | File | What it does |
|---|---|---|
| Loading | `carcux_correlation/data.py` | Reads a CARCUX-BD export. An observation belongs to every event it supports, partially supports, contradicts or is related to; `unrelated` is a hard negative. Child events are folded into their root for partition measures. Unannotated observations are left out of scoring. |
| Pair features | `features.py` | Meaning: character n-gram TF-IDF cosine (works across Bangla, Banglish and English without a tokenizer; a multilingual sentence encoder can replace it). Place: great-circle km, and km scaled by both locations' `precision_m`; a missing location is flagged, never guessed. Time: hours apart. Type: same type, same family, or unknown. |
| Scorers | `models.py` | **B1 `text`**: text similarity only. **B2 `text+rules`**: text similarity, set to zero where the current CARCUX rule says no (beyond 48 h, or beyond 5 km plus both locations' uncertainty, capped at 300 km). **`joint`** (proposed): logistic regression over all features. **`joint-space`**, **`joint-time`**: the joint model without place or without time features (ablations). |
| Clustering | `models.py` | The same for every scorer. Observations arrive in time order; each joins the most similar existing cluster (average over its members) if the similarity reaches a threshold, else starts a new one. The threshold is tuned on training folds only, by B-cubed F1. |
| Metrics | `metrics.py` | Pairwise precision/recall/F1 (a pair is positive if the two share any gold event), extended B-cubed for overlapping gold (Amigó et al., 2009), adjusted Rand index against one root event per observation. |
| Evaluation | `evaluate.py` | k-fold cross-validation grouped by root event (no event is split between training and testing), seeded; mean ± sd over folds. |
| Simulation | `simulate.py` | A seeded, clearly labelled simulated CARCUX-BD set for development (below). |
| Streaming | `stream.py` | The same features, methods and clustering for large datasets: each item is compared only with earlier items, and many thresholds are clustered in one pass. Train/test protocol. |
| Benchmarks | `benchmarks/news_clustering.py` | Loader and runner for the public news stream clustering benchmark (below). |

## Run it

From `ai/correlation` (Python 3.12; the validator package comes from `data/tools`):

```bash
pip install -e ../../data/tools -e ".[dev]"

# Evaluate on any CARCUX-BD export (for example one downloaded from the /dataset page)
python -m carcux_correlation.evaluate path/to/export --folds 5 --seed 0 --json results.json

# Make a simulated set, check it, evaluate on it
python -m carcux_correlation.simulate /tmp/sim --events 80 --seed 1
python -m carcux_data.validate /tmp/sim
python -m carcux_correlation.evaluate /tmp/sim

pytest -q && ruff check . && ruff format --check .
```

On Windows PowerShell, use a folder such as `$env:TEMP\sim` in place of `/tmp/sim`.

## The simulated test bed

Real annotated data is not big enough yet to tell methods apart, so `simulate.py` produces a stress set that is valid CARCUX-BD. **It is not evidence about real events.** Every observation has `is_simulated: true`, every event title starts with `[SIMULATED]`, and every reference is under `example.org/simulated/`. It covers the hard cases on purpose:

- reports in English, Bangla and Banglish about the same event, which share few characters;
- GPS (≈250 m error), district only (`precision_m` 30 000), or no location (≈30 %);
- twins: the same kind of event at the same place days later, or in the nearest district at the same hours;
- a different event at the same place and hour;
- child road blockages under waterlogging and floods, with some reports about both;
- false events, with reports that deny them (`contradicts`);
- a noisy type claim (10 % wrong, 20 % missing), as the keyword classifier gives in practice.

### First results (simulated, 3 sets × 80 seed events, 5-fold grouped CV)

B-cubed F1, mean over folds:

| Method | sim seed 1 | sim seed 2 | sim seed 3 |
|---|---|---|---|
| B1 text | 0.609 | 0.525 | 0.638 |
| B2 text + rules | 0.780 | 0.730 | 0.755 |
| **joint** | **0.954** | **0.934** | **0.932** |
| joint without place | 0.892 | 0.872 | 0.875 |
| joint without time | 0.767 | 0.754 | 0.765 |

Pairwise F1 for the joint model is 0.86–0.91, against 0.15–0.19 for text alone and 0.47–0.63 for text + rules.

**Read this carefully.** The simulator was written by the same people as the model, and its reports are short template sentences, so the absolute numbers are optimistic. All the comparison shows is that the pipeline can measure the effect RQ1 asks about, and that the effect goes the expected way when place and time carry real signal. The paper's claims have to come from real CARCUX-BD annotations (and CrisisFACTS), using the same command.

## Public benchmark: multilingual news stream clustering

No public dataset has what CARCUX needs all together: reports labelled with the incident
they describe, plus time, place and Bangla. We checked CrisisFACTS (labels are facts and
whole disasters, with no locations), the Twitter event corpora (tweet IDs only; the text
now needs the paid X API), SemEval-2022 Task 8 (rated article pairs) and a Bangladesh
flood news corpus (flood / not flood labels; the data is not confirmed public). The
closest fit is the stream clustering benchmark of **Miranda et al. (EMNLP 2018)**:

- English, German and Spanish news, labelled with fine-grained story clusters, with times;
- the same task as ours: articles arrive in order and are clustered online;
- **no coordinates**, so it tests meaning and time, and it cannot test place. Place is
  tested only on CARCUX-BD; that gap is part of what CARCUX-BD contributes.

The files are not in this repository (about 100 MB, and their licence is not stated).
Download them to a folder outside the repo. On Windows PowerShell:

```powershell
mkdir D:\benchmarks\news-clustering -Force
cd D:\benchmarks\news-clustering
$base = "ftp://ftp.priberam.pt/SUMMAPublic/Corpora/Clustering/2018.0"
curl.exe -u "ftp.priberam.pt|anonymous:" -O "$base/dataset/dataset.dev.json"
curl.exe -u "ftp.priberam.pt|anonymous:" -O "$base/dataset/dataset.test.json"
```

Then, from `ai/correlation`:

```bash
python -m carcux_correlation.benchmarks.news_clustering D:\benchmarks\news-clustering --json news.json
```

The protocol follows the authors' scorer: one language at a time, articles in date order,
every article counted, pairwise precision/recall/F1 against `cluster`. Methods are
trained and tuned on `dataset.dev.json` and reported on `dataset.test.json`. The table
also shows the paper's best pairwise F1 for reference (0.941 en, 0.971 de, 0.942 es);
that system used lemmas, named entities and learned ranking, so it is a ceiling to
compare against rather than a like-for-like baseline. `joint-space` is left out because
no article has a location. `--text char` switches to the character n-grams used on
CARCUX-BD (the default for news is word TF-IDF). English takes about 4 minutes and
under 0.5 GB of memory.

This runs through `stream.py`, which compares each item only with earlier items and
gives the same features, clusters and scores as the all-pairs code (checked by tests).

## Still to do

- Run on real annotated CARCUX-BD exports once the case studies are labelled.
- Swap the TF-IDF encoder for a multilingual sentence encoder and compare.
- Use `unrelated` hard negatives in training, not only in scoring.
- Predict `parent_event_id` links (they are currently folded into the root event for scoring).
- Significance testing across folds and seeds for the paper.
- Serve the model in the backend once it beats B2 on real data.
