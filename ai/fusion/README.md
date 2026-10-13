# 3 · Fusion: evidence under conflict

**Role:** ⭐ **research core (Q1 paper)** · **Spec:** §5.1 (RQ2–RQ5), §7 · **Status:** first stage built: evaluation harness, contamination simulator, copy detection, baselines B3–B5 and a dependence-aware reliability model; checked on simulated data only. Conflict detection (RQ3), the calibration study (RQ5), the LLM baseline (B6) and real-data runs are next.

Given an event and its observations, decides **which sources are really independent, where they conflict, and how certain the assessment is**, and keeps those answers calibrated as the information gets noisier.

## In → out

| In | Out (schema v1) |
|---|---|
| Event cluster + observations + sources | `dependences`: who copied whom (`verbatim_copy`, `rewrite`, `repost`, `cites`, `same_media`) |
| | `relations`: stance and per-attribute `conflicts` |
| | Assessment over time: `verified` / `partially_verified` / `conflicting` / `unverified` / `refuted` / `insufficient_evidence`, with a **calibrated probability** |

## Research questions

- **RQ2:** Does modelling source dependence beat treating every source as independent?
- **RQ3:** Does explicit conflict detection reduce wrong assessments?
- **RQ4:** How fast does performance degrade as contamination rises from 0 % to 60 %?
- **RQ5:** Are the probabilities calibrated, and do multi-state outputs beat a single confidence score?

## What is built

| Part | File | What it does |
|---|---|---|
| Loading | `carcux_fusion/data.py` | Reads a CARCUX-BD export: for each event, whether it happened (`ground_truth.occurred`) and every linked observation as a vote (supports and partly supports +1, contradicts −1); sources and their types; gold dependences. |
| Task | `evaluate.py` | For each event, at T+1h, T+6h, T+24h and final (7 days) after its first observation, the probability it really happened from the evidence published by then. Events in 5 seeded folds; everything learned (source reliability, copy threshold, calibration) comes from the other folds. |
| Metrics | `metrics.py` | Brier score, log loss, expected calibration error (10 bins), accuracy, AUC, reliability-diagram bins. Brier differences between methods get a paired bootstrap over events (95 % interval, p). |
| Copy detection | `dependence.py` | Each item against earlier items about the same event: character n-gram text overlap, attribution phrases ("according to", "er moto", "এর মতে", "RT", …), perceptual-hash distance of photos, publication order. Text threshold tuned on training events. Scored against gold dependences (precision, recall, F1, and whether the predicted origin is in the right copy cascade). |
| Methods | `methods.py` | **B3 `majority`**, **B4 `equal`** (one vote per item), **B5 `truthfinder`** (unsupervised iterative source trust), `truthfinder-dep` (the same, each copy cascade once). Supervised source reliability (how often a source's reports turned out right on training events, shrunk to its source type): `reliability` (every item counts), `reliability-dedup` (copies dropped), **`reliability-dep` (proposed)**: originals count with their sources' first-hand reliability, copies form a second channel with each copier's own record as a copier, and the calibration learns how much each channel weighs; `reliability-oracle` is the same with gold dependences. Every method's score goes through the same Platt calibration fitted on training events. |
| Simulator | `simulate.py` | Valid CARCUX-BD with a contamination dial (below). |
| RQ4 sweep | `sweep.py` | Contamination 0–60 %, several seeds, all methods. |

## Run it

From `ai/fusion` (Python 3.12; uses the dataset validator and the correlation module's text tools):

```bash
pip install -e ../../data/tools -e ../correlation -e ".[dev]"

python -m carcux_fusion.simulate /tmp/fus --events 120 --contamination 0.3 --seed 1
python -m carcux_data.validate /tmp/fus
python -m carcux_fusion.evaluate /tmp/fus --json fusion.json     # any CARCUX-BD export works
python -m carcux_fusion.sweep --seeds 3 --json sweep.json         # RQ4, about 10 minutes

pytest -q && ruff check . && ruff format --check .
```

On Windows PowerShell use a folder such as `$env:TEMP\fus` in place of `/tmp/fus`.

## The simulator

**Not evidence about real events:** every source, event and item says it is simulated. It models:

- **sources with a hidden reliability** around their type's mean (field workers 0.90, news 0.85, the official disaster office 0.97, social accounts 0.65, rumour accounts 0.20); an item's stance is right with that probability. The reliability is written in each source's `notes` for analysis; no method reads it;
- **real and false events**: a false event exists because someone claimed it, and careful sources then tend to deny it;
- **copies**: verbatim, reworded, reposted, cited, or the photo reused, repeating their origin's stance, with gold dependences for every copy;
- **time**: first reports within hours; the official office confirms or denies 6 to 30 hours later;
- **contamination** (0 to 0.6, the share of all items that are injected): rumours amplified by copy cascades, false denials of real events, extra amplification of false claims. Injected items mostly come from **accounts never seen before** (60 %), some from **hijacked credible accounts** (20 %), the rest from known rumour accounts. Injected events are marked so the **clean events** (identical at every level, same seed) can be scored on their own.

Schema v1.2 added the simulation kind `source_report` for original simulated items from non-field sources.

## Results so far (simulated only)

### A design correction first

The first version of the sweep made learned-reliability methods look *better* as contamination rose (final Brier 0.075 → 0.016). That was the experiment's fault, not a finding: the same few rumour accounts appeared in training and test events, so the model learned their names, and every injected rumour added an easy false event to the scores. Injected items now come mostly from unseen or hijacked accounts, and the sweep reports the clean events separately. Only the corrected results are below.

### RQ4: contamination 0–60 % (3 seeds, 120 seed events, 5-fold CV)

Final Brier score on the **clean events** (lower is better; 0.25 is a coin flip; seed-to-seed spread mostly ≤ 0.02):

| Method | 0 % | 10 % | 20 % | 30 % | 40 % | 50 % | 60 % |
|---|---|---|---|---|---|---|---|
| B3 majority | 0.130 | 0.141 | 0.172 | 0.223 | 0.277 | 0.336 | 0.366 |
| B4 equal | 0.131 | 0.141 | 0.170 | 0.216 | 0.270 | 0.335 | 0.391 |
| B5 truthfinder | 0.128 | 0.139 | 0.167 | 0.214 | 0.269 | 0.329 | 0.326 |
| truthfinder-dep | 0.071 | 0.078 | 0.091 | 0.114 | 0.146 | 0.207 | 0.320 |
| reliability (copies counted) | 0.095 | 0.094 | 0.090 | 0.084 | 0.069 | 0.067 | 0.073 |
| reliability-dedup (copies dropped) | 0.074 | 0.078 | 0.082 | 0.102 | 0.101 | 0.112 | 0.112 |
| **reliability-dep (proposed)** | **0.075** | **0.082** | **0.084** | **0.091** | **0.080** | **0.069** | **0.085** |
| reliability-oracle (gold copies) | 0.077 | 0.078 | 0.081 | 0.089 | 0.080 | 0.069 | 0.081 |

At T+6h the picture is the same, with higher errors (B3 0.149 → 0.365; proposed 0.135 → 0.166). Copy detection F1 on held-out events: 0.97–0.99.

What this supports, on simulated data:

- **RQ4:** methods that treat every item as an independent, equally trustworthy vote degrade fast; by 40 % contamination they are worse than a coin flip on the very same events. Counting copies once (`truthfinder-dep`) roughly halves the error up to 30 % but collapses by 60 %. Learning which sources have been right before keeps the error below 0.11 across the whole range.
- **RQ2, without labels:** dependence modelling matters a lot (`truthfinder-dep` vs `truthfinder`).
- **RQ2, with learned reliability:** the effect is mixed. Dropping copies helps on clean data (0.074 vs 0.095) but hurts under heavy contamination (0.112 vs 0.073), because who amplifies a claim is itself evidence. Keeping copies as a separate channel (the proposed model) gets most of both, but plain counting is still slightly better at 50–60 %. Detected dependences are as good as gold ones here.

**Caveats for the paper.** The simulator and the methods were written together, and simulated copies follow the simulator's own phrasing, so copy detection (F1 ≈ 0.98) and every absolute number are optimistic. The supervised methods learn from events drawn from the same simulated world they are tested on. The design was corrected once after seeing results (above), on simulated data only. The claims must come from real CARCUX-BD dependences and stances, run with the same commands.

## Baselines

Majority vote (B3), equal-weight fusion (B4), established truth discovery (B5), LLM-given-all-observations (B6, not yet built).

## Still to do

- **RQ3:** attribute-level conflict detection (place, time, magnitude, counts, cause) and whether it reduces wrong assessments.
- **RQ5:** calibration study: raw vs calibrated, temperature scaling or evidential outputs, reliability diagrams; the six-label assessment against gold checkpoint labels, versus a single probability.
- **B6:** an LLM given all observations.
- Real CARCUX-BD runs once stances and dependences are annotated.
- In the product: an assessment suggestion on each event, measured against analysts the way event suggestions are.
