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
| Cluster-level model | `cluster_model.py` | **`cjoint`** (proposed, second design): decides join-or-new against each candidate cluster as a whole: centroid and best-member text similarity, hours since the cluster's newest member and its age, its size, distance to its nearest located member, and type agreement. Trained on the same decision, walking the training stream with gold clusters. Candidates are the 20 clusters most similar in text. **`ctext`**: the same model with meaning (and size) only, the fair text baseline. **`cjoint-space`**, **`cjoint-time`**: ablations. Two recency terms (text similarity × time since newest member; time since newest member relative to the cluster's usual gap) let a strong text match tolerate a longer silence; **`cjoint-recency`** drops just those. Thresholds are searched in steps of 0.05, then 0.01 around the best. |
| Significance | `significance.py` | Paired bootstrap over test stories: both methods' B-cubed F1 on the same resamples of whole gold stories, giving a 95 % confidence interval and p-value for the difference. |
| Clustering | `models.py` | The same for every pair-level scorer. Observations arrive in time order; each joins the most similar existing cluster (average over its members) if the similarity reaches a threshold, else starts a new one. The threshold is tuned on training folds only, by B-cubed F1. |
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

### Results (simulated, 3 sets × 80 seed events, 5-fold grouped CV)

B-cubed F1, mean over folds:

| Method | sim seed 1 | sim seed 2 | sim seed 3 |
|---|---|---|---|
| B1 text (pair level) | 0.609 | 0.525 | 0.638 |
| B2 text + rules | 0.780 | 0.730 | 0.755 |
| joint, pair level (first design) | 0.954 | 0.934 | 0.932 |
| joint without place | 0.892 | 0.872 | 0.875 |
| joint without time | 0.767 | 0.754 | 0.765 |
| ctext, cluster level (text baseline) | 0.594 | 0.517 | 0.623 |
| **cjoint, cluster level (with recency terms)** | **0.951** | **0.949** | **0.935** |
| cjoint without place | 0.911 | 0.886 | 0.853 |
| cjoint without time | 0.685 | 0.706 | 0.767 |

Pairwise F1 for `cjoint` is 0.88–0.93, against 0.11–0.18 for `ctext` and 0.47–0.63 for text + rules.

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
# for the paper: three training seeds (about three times longer)
python -m carcux_correlation.benchmarks.news_clustering D:\benchmarks\news-clustering --seeds 3 --json news-3seeds.json
```

It runs B1, B2, `ctext`, `cjoint`, `cjoint-time` and `cjoint-recency` (add
`--with-pair-joint` for the failed first design), then tests four differences with the
paired story bootstrap: `cjoint` against `ctext` (RQ1, like for like), against B1,
against B2, and against itself without the recency terms. The bootstrap measures
uncertainty from which stories are in the test set; `--seeds` measures training
randomness. Per-item scores come from the full clustering, which is not re-run per
resample.

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
With the cluster-level methods, English takes about 11 minutes on a 2-CPU machine and
under 0.5 GB of memory.

### First run: the pair-level joint model failed

B-cubed F1 on the test sets, first design (13 October 2026):

| Method | English | German | Spanish |
|---|---|---|---|
| B1 text | 0.830 | 0.867 | **0.912** |
| B2 text + rules | **0.921** | **0.935** | 0.900 |
| joint, pair level | 0.539 | 0.744 | 0.799 |
| joint without time | 0.834 | 0.857 | 0.910 |

Pairwise F1 for B2 was 0.935 / 0.991 / 0.957 (paper's best: 0.941 / 0.971 / 0.942).
Pairwise F1 is dominated by a few very large stories (one has 1,869 articles), so these
are not claims of beating the paper.

Time clearly helps (B2 beats B1 in English and German), but the pair-level joint model
used it badly. It averages pair scores over every member of a cluster, and it learned
that items far apart in time are different events. News stories run for weeks, so a new
article looked unlike a long story's older members, the average fell, and the story was
split again and again (English: 222 stories became 1,159 clusters). The simulator hid
this because its reports arrive within hours of their event. Floods and waterlogging in
CARCUX also last days, so this matters beyond the benchmark.

The second design (`cluster_model.py`) makes the decision against the cluster as a
whole, using time since the cluster's newest member rather than the time to every
member.

### Second run: the cluster-level model

B-cubed F1 on the test sets (13 October 2026, one run, seed 0):

| Method | English | German | Spanish |
|---|---|---|---|
| B1 text, pair level | 0.830 | 0.867 | 0.912 |
| B2 text + rules | **0.921** | **0.935** | 0.900 |
| joint, pair level (first design) | 0.539 | 0.744 | 0.799 |
| `ctext`, cluster level, meaning only | 0.799 | 0.803 | 0.866 |
| **`cjoint`, cluster level, meaning + time** | 0.914 | 0.885 | **0.935** |

| `cjoint` | English | German | Spanish |
|---|---|---|---|
| Pairwise P / R / F1 | 0.973 / 0.862 / 0.914 | 0.997 / 0.630 / 0.772 | 0.987 / 0.975 / 0.981 |
| Clusters (gold) | 429 (222) | 185 (118) | 202 (149) |

What this shows, and what it does not:

- **RQ1, like for like:** with the same model and only the time features added,
  `cjoint` beats `ctext` in all three languages (+0.115, +0.082, +0.069 B-cubed F1).
  `cjoint-time` scored exactly the same as `ctext` (no article has a place or type, so
  removing time leaves the same model), which is a useful sanity check.
- **The fix worked:** English went from 1,159 clusters to 429, and B-cubed F1 from
  0.539 to 0.914.
- **The learned model does not yet beat the simple rule everywhere.** B2 (text + a
  48-hour cut-off) is still slightly ahead in English and clearly ahead in German, where
  there is the least training data (4,043 articles). `cjoint` is best in Spanish.
- **Text alone is weaker at cluster level** than pair level (`ctext` 0.799 vs B1 0.830
  in English), so part of `cjoint`'s gain over `ctext` restores what the cluster-level
  set-up loses. The fair statement is the like-for-like one above.
- **Not claims of beating the paper:** pairwise F1 is dominated by a few huge stories,
  this is one run with one seed, and the threshold grid is coarse (steps of 0.05).
  Significance testing over seeds is still to do.
- **Place is not tested here:** no article has coordinates. That still needs CARCUX-BD.

## Still to do

- Run on real annotated CARCUX-BD exports once the case studies are labelled.
- Swap the TF-IDF encoder for a multilingual sentence encoder and compare.
- Use `unrelated` hard negatives in training, not only in scoring.
- Predict `parent_event_id` links (they are currently folded into the root event for scoring).
- Significance testing across folds and seeds for the paper (and on the news benchmark).
- Close the gap to B2 in German: more training pairs, a finer threshold grid, or a
  learned recency term; and check why `ctext` trails pair-level text.
- Serve the model in the backend once it beats B2 on real data.
