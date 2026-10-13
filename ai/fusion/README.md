# 3 · Fusion: evidence under conflict

**Role:** ⭐ **research core (Q1 paper)** · **Spec:** §5.1 (RQ2–RQ5), §7 · **Status:** evaluation harness, contamination simulator, copy detection, baselines B3–B5, a dependence-aware reliability model (RQ2, RQ4), and detail-level conflict detection with the six-label assessment (RQ3); checked on simulated data only. The calibration study (RQ5), the LLM baseline (B6) and real-data runs are next.

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
| Details in dispute | `conflict.py` | Per detail (magnitude, number affected, deaths, cause): the claims of one report per copy cascade, each weighted by its source's learned reliability; **disputed** when two credible claims disagree (affected counts within 25 % agree, deaths must match); the best estimate by weighted mode or median. |
| Assessment | `assess.py` | The dataset's six labels at each checkpoint, from the probability it happened, whether a detail is disputed, and credible reports on each side; thresholds tuned on training folds. Compared with and without conflict detection (RQ3), and against annotated conflicts as an upper bound. |
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
python -m carcux_fusion.assess /tmp/fus                           # RQ3 on one dataset
python -m carcux_fusion.assess --simulate --seeds 3               # RQ3 at 0, 30, 60 %

pytest -q && ruff check . && ruff format --check .
```

On Windows PowerShell use a folder such as `$env:TEMP\fus` in place of `/tmp/fus`.

## The simulator

**Not evidence about real events:** every source, event and item says it is simulated. It models:

- **sources with a hidden reliability** around their type's mean (field workers 0.90, news 0.85, the official disaster office 0.97, social accounts 0.65, rumour accounts 0.20); an item's stance is right with that probability. The reliability is written in each source's `notes` for analysis; no method reads it;
- **real and false events**: a false event exists because someone claimed it, and careful sources then tend to deny it;
- **details** (generator 0.2): each event has a true magnitude, number affected, death toll and cause; first-hand reports state one to three of them, right with a probability that rises with the source's reliability (wrong numbers mostly exaggerated). A report with a wrong detail is `partially_supports` with that detail in `conflicts`, as annotators record it. Copies repeat their origin's details. The gold label becomes `partially_verified` when credible first-hand reports disagree on a detail. Details use their own random stream, so everything else is generated exactly as in 0.1 (a test checks this);
- **copies**: verbatim, reworded, reposted, cited, or the photo reused, repeating their origin's stance, with gold dependences for every copy;
- **time**: first reports within hours; the official office confirms or denies 6 to 30 hours later;
- **contamination** (0 to 0.6, the share of all items that are injected): rumours amplified by copy cascades, false denials of real events, extra amplification of false claims. Injected items mostly come from **accounts never seen before** (60 %), some from **hijacked credible accounts** (20 %), the rest from known rumour accounts. Injected events are marked so the **clean events** (identical at every level, same seed) can be scored on their own.

Schema v1.2 added the simulation kind `source_report` for original simulated items from non-field sources.

## Results so far (simulated only)

### A design correction first

The first version of the sweep made learned-reliability methods look *better* as contamination rose (final Brier 0.075 → 0.016). That was the experiment's fault, not a finding: the same few rumour accounts appeared in training and test events, so the model learned their names, and every injected rumour added an easy false event to the scores. Injected items now come mostly from unseen or hijacked accounts, and the sweep reports the clean events separately. Only the corrected results are below.

### RQ4: contamination 0–60 % (3 seeds, 120 seed events, 5-fold CV, generator 0.2)

Final Brier score on the **clean events** (lower is better; 0.25 is a coin flip; seed-to-seed spread mostly ≤ 0.02):

| Method | 0 % | 10 % | 20 % | 30 % | 40 % | 50 % | 60 % |
|---|---|---|---|---|---|---|---|
| B3 majority | 0.130 | 0.141 | 0.172 | 0.223 | 0.277 | 0.336 | 0.366 |
| B4 equal | 0.131 | 0.141 | 0.170 | 0.216 | 0.270 | 0.335 | 0.391 |
| B5 truthfinder | 0.128 | 0.139 | 0.167 | 0.214 | 0.269 | 0.329 | 0.326 |
| truthfinder-dep | 0.069 | 0.074 | 0.089 | 0.111 | 0.143 | 0.178 | 0.328 |
| reliability (copies counted) | 0.095 | 0.094 | 0.090 | 0.084 | 0.069 | 0.067 | 0.073 |
| reliability-dedup (copies dropped) | 0.074 | 0.076 | 0.080 | 0.102 | 0.102 | 0.112 | 0.114 |
| **reliability-dep (proposed)** | **0.077** | **0.079** | **0.083** | **0.090** | **0.078** | **0.071** | **0.083** |
| reliability-oracle (gold copies) | 0.077 | 0.078 | 0.081 | 0.089 | 0.080 | 0.069 | 0.081 |

At T+6h the picture is the same, with higher errors (B3 0.149 → 0.365; proposed 0.135 → 0.164). Copy detection F1 on held-out events: 0.99. Generator 0.1 gave the same rows for every method that ignores copies, and differences of at most 0.03 for the others: copies now also repeat their origin's details, which makes them slightly easier to spot.

What this supports, on simulated data:

- **RQ4:** methods that treat every item as an independent, equally trustworthy vote degrade fast; by 40 % contamination they are worse than a coin flip on the very same events. Counting copies once (`truthfinder-dep`) roughly halves the error up to 50 % but collapses by 60 %. Learning which sources have been right before keeps the error below 0.11 across the whole range.
- **RQ2, without labels:** dependence modelling matters a lot (`truthfinder-dep` vs `truthfinder`).
- **RQ2, with learned reliability:** the effect is mixed. Dropping copies helps on clean data (0.074 vs 0.095) but hurts under heavy contamination (0.112 vs 0.073), because who amplifies a claim is itself evidence. Keeping copies as a separate channel (the proposed model) gets most of both, but plain counting is still slightly better at 50–60 %. Detected dependences are as good as gold ones here.

### RQ3: does explicit conflict detection reduce wrong assessments?

Six-label assessment against the gold checkpoint labels (3 seeds, 120 seed events, 5-fold CV; all variants use the proposed model's probabilities, except the last):

| Final checkpoint | 0 % | 30 % | 60 % |
|---|---|---|---|
| **Wrongly called verified**, probability only | 30.6 % | 20.1 % | 12.8 % |
| **Wrongly called verified**, with conflict detection | **6.7 %** | **4.7 %** | **5.7 %** |
| Wrongly called verified, annotated conflicts | 6.7 % | 4.7 % | 5.7 % |
| Macro-F1, probability only | 0.434 | 0.406 | 0.301 |
| Macro-F1, with conflict detection | **0.593** | **0.580** | **0.460** |
| Macro-F1, annotated conflicts | 0.596 | 0.582 | 0.462 |
| Macro-F1, majority vote, probability only | 0.229 | 0.202 | 0.219 |
| F1 on "partially verified", with conflict detection | 0.848 | 0.891 | 0.843 |

At T+6h: wrongly verified 24.2 % → 8.3 % at 0 %, 11.3 % → 7.8 % at 60 %.

Details right (an estimate matching the truth; final checkpoint, all levels within 0.01):

| Strategy | Right |
|---|---|
| The first report's value | 0.853 |
| Most common value over every item | 0.876 |
| Most common value, one per copy cascade | **0.896** |
| One per cascade, weighted by source reliability | 0.876–0.888 |

What this supports, on simulated data:

- **RQ3: yes, for the costly error.** Without conflict detection, an event whose details credible sources dispute is called "verified"; with it, events wrongly called verified fall from 13–31 % to about 5–7 % at every contamination level. Detected disputes do as well as the annotated ones.
- The macro-F1 gain is partly by construction: without conflict detection the system cannot say "partially verified" at all. The wrongly-verified rate is the fair comparison.
- **Counting each copy cascade once gets details right more often** than trusting the first report or counting every item; weighting by source reliability does not add to that here (the reliability is learned on whether events happened, not on details).
- Contamination in this simulator attacks whether events happened, not their details (injected items carry no details for real events), so detail accuracy does not move with contamination. Contaminated details are a gap to close.

**Caveats for the paper.** The simulator and the methods were written together, and simulated copies follow the simulator's own phrasing, so copy detection (F1 ≈ 0.98) and every absolute number are optimistic. The supervised methods learn from events drawn from the same simulated world they are tested on. The design was corrected once after seeing results (above), on simulated data only. The gold checkpoint labels come from a rule the simulator applies (a careful analyst's rule), and the assessment is tuned against them, so agreement with that rule is partly built in; real labels come from annotators. The claims must come from real CARCUX-BD dependences and stances, run with the same commands.

## Baselines

Majority vote (B3), equal-weight fusion (B4), established truth discovery (B5), LLM-given-all-observations (B6, not yet built).

## Still to do

- **RQ3, next steps:** place and time disputes; contamination that attacks details; detail reliability learned per source.
- **RQ5:** calibration study: raw vs calibrated, temperature scaling or evidential outputs, reliability diagrams; whether the six labels serve analysts better than a single probability.
- **B6:** an LLM given all observations.
- Real CARCUX-BD runs once stances and dependences are annotated.
- In the product: an assessment suggestion on each event, measured against analysts the way event suggestions are.
