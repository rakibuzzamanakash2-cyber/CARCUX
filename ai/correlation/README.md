# 4 · Correlation: which observations describe the same event?

**Role:** ⭐ **research core (Q1 paper)** · **Spec:** §5.1 (RQ1), §7.2 · **Status:** not started

Groups a stream of observations into real-world events using **meaning, place and time together**, and links child events to parents (a road blockage caused by waterlogging).

## In → out

| In | Out (schema v1) |
|---|---|
| Observations with claims, `location_mentions`, `published_at` / `observed_at` | Event clusters: observation → `event_id` |
| | `parent_event_id` links |
| | `unrelated` decisions (hard negatives rejected) |

## Research question

**RQ1:** Does jointly modelling semantic, spatial and temporal similarity improve event correlation compared with semantic similarity alone?

## Planned method

- Learned pairwise similarity combining text embeddings, geodesic distance (scaled by each location's `precision_m`) and time gap
- Incremental (online) clustering, since observations arrive as a stream
- Baselines: text-only clustering (B1), text then rule-based space/time filters (B2)

## Evaluation

Pairwise precision/recall/F1, B-cubed, adjusted Rand index on CARCUX-BD and CrisisFACTS; ablations removing spatial and temporal features.
