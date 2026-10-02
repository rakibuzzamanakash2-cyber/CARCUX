# 6 · Decision support: helping humans decide

**Role:** engineered now, evaluated after deployment · **Spec:** §6, §8.3, §9.5 · **Status:** not started · **Candidate 2nd paper**

Turns fused events into something staff can act on quickly, **without hiding the evidence or making decisions for them.**

## In → out

| In | Out |
|---|---|
| Events with assessments, relations, dependences | **Priority** (HIGH / MEDIUM / LOW) from operational factors only: safety risk, people/areas affected, disruption, rate of change, duration, confidence |
| | **Evidence-referenced summaries:** every sentence cites observation ids |
| | **Assistant answers** to questions like "what changed in the last hour?", always with evidence references |
| | **Review queue** ordering for analysts |

## Rules

- Priority **never** depends on who is involved or what anyone said about anyone (Spec §8.3).
- The assistant reads the evidence graph as data. It has **no** write access and no privileged tools (Spec §9.3).
- An answer that cannot point to evidence says so instead of guessing.

## Evaluation (after deployment)

User study with staff: time to understand an event, evidence retrieval time, verification accuracy, workload. This is the basis for a possible second paper.
