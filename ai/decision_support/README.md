# 6 · Decision support: helping humans decide

**Role:** engineered now, evaluated after deployment · **Spec:** §6, §8.3, §9.5 · **Status:** suggested priority, evidence-cited summaries and "what changed" built (standard library only) and in the product on each event's overview; whether analysts follow the suggested priority is logged and measured. The user study comes after deployment. **Candidate 2nd paper**

Turns fused events into something staff can act on quickly, **without hiding the evidence or making decisions for them.**

## In → out

| In | Out |
|---|---|
| An event with its linked evidence: each item's source, stance, details, its source's reliability, and whether it repeats another item; the fused estimate of each detail | **Suggested priority** (critical / high / medium / low) with a reason for every point |
| | **Summary:** every sentence cites the items it rests on; with no evidence it says so instead of guessing |
| | **What changed** since a moment: new items, new denials, counts that moved, analysts' decisions |

```python
from carcux_decision_support import EventFacts, suggest, summarise, what_changed
p = suggest(event, now)            # PrioritySuggestion(level, score, factors)
for s in summarise(event):         # Sentence(text, cites, kind)
    print(s.text, s.cites)
```

## Priority: operational factors only

| Factor | Points |
|---|---|
| Hazard of the kind of event | 3 (fire, collapse, explosion, cyclone, flash flood, earthquake, landslide …), 2 (flood, erosion, accidents, bridge damage), 1 otherwise |
| Deaths (fused estimate) | 4 for 10 or more, 2 for 1–9 |
| People affected | 3 for 100,000+, 2 for 10,000+, 1 for 1,000+ (households × 4) |
| Water waist-deep or worse | 1 |
| Road and infrastructure (stops movement or services) | 1 |
| Growing: 3+ new reports in 2 hours; deaths up 20 %+ in a day | 1 each |
| Ongoing for 48 hours or more | 1 |
| Doubt: refuted −4; under 30 % likely −3; only one source −1 | |

Critical from 8 points, high from 5, medium from 3. **Priority never depends on who is involved or what anyone said about anyone** (Spec §8.3): a test renames every source and checks that nothing changes. Sources are counted by who they are, not by name shown, so field workers, who all appear as "A field worker", still count as separate sources.

## Summaries

The lead (what, where, since when), how many sources say it happened and how many deny it (credible ones in brackets), each denial with its words, each detail with who says it ("71 dead, as Daily Star and bdnews24 say. Earlier reports gave 23, 52, 54 as the figure rose"), disputes with both sides (counts only compared when said within 12 hours, guideline v0.4), details analysts marked wrong, copies counted once, and the latest item. A sentence that cannot cite evidence is not written.

## In the product

`backend/app/decision_support` is a checked copy (`backend/scripts/sync_decision_support.py`; `tests/test_decision_support_copy.py` fails when they differ). `backend/app/services/briefing.py` fills the module from the database, and `GET /api/v1/events/{id}/briefing?hours=24` serves it to analysts. The event overview shows **CARCUX briefing** (each citation number opens the item in the Evidence tab) and **Suggested priority** with a button to take it.

When an analyst sets a priority, the suggestion at that moment and whether it was followed go into the audit log, as for stance and assessment suggestions:

```bash
python -m app.cli evaluate-priority     # in the backend container
```

## Run it

```bash
pip install -e ".[dev]"
pytest -q && ruff check . && ruff format --check .
```

## Evaluation (after deployment)

- Now: how often analysts follow the suggested priority, and how far apart they are when not (`evaluate-priority`).
- After deployment: a user study with staff: time to understand an event, evidence retrieval time, verification accuracy, workload. This is the basis for a possible second paper.

## Not yet

- A free-text assistant ("what changed in Mirpur since noon?") over the same evidence, with the same rule: no answer without citations, no write access, no privileged tools (Spec §9.3).
- Ordering the review queue by suggested priority.
