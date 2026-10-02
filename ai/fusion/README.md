# 3 · Fusion: evidence under conflict

**Role:** ⭐ **research core (Q1 paper)** · **Spec:** §5.1 (RQ2–RQ5), §7 · **Status:** not started

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

## Planned components

1. **Dependence detection:** text overlap, attribution, media hashes, timestamp order
2. **Conflict detection:** attribute-level comparison and NLI-style contradiction
3. **Aggregation:** truth-discovery / Bayesian / graph-based over the evidence graph, counting copies once
4. **Calibration:** temperature scaling or evidential outputs; ECE, Brier score, reliability diagrams

## Baselines

Majority vote (B3), equal-weight fusion (B4), established truth discovery (B5), LLM-given-all-observations (B6).
