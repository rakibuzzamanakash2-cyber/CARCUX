# CARCUX

**AI Situational Intelligence Platform**

CARCUX fuses authenticated field observations with noisy public information (news, public posts, images, video) into evidence-backed, uncertainty-aware event intelligence. Its research focus is **source-aware spatiotemporal evidence fusion for disaster and disruption events in Bangladesh**.

> Observe → Correlate → Verify → Understand → Human Decision
> AI assists; humans decide.

## Repository layout

| Path | Contents |
|---|---|
| `backend/` | FastAPI service: auth, field reports, events, evidence, audit log, workers |
| `frontend/` | Next.js intelligence dashboard and field PWA |
| `ai/extraction/` | Language ID, Bangla/Banglish/English NLP, geocoding |
| `ai/media/` | ASR, OCR, image embeddings and hashing |
| `ai/fusion/` | Research core: correlation, source dependence, conflict, calibration |
| `data/` | Dataset schema, annotation guideline, samples, dataset card (CARCUX-BD) |
| `research/` | Literature notes, baselines, experiments, ablations, robustness, results |
| `deployment/` | Docker, Compose, deployment configuration |
| `docs/` | Specification, architecture, security, threat model, API |
| `tests/` | Cross-component and integration tests |

## Tracks

Work runs in three parallel tracks — **Code**, **Dataset**, **Paper** — as described in the Spec v1.0. Use the matching label on every issue and PR.

## Getting started

See `backend/README.md` once the backend skeleton is merged.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) before your first commit. Short version: branch from `main`, use Conventional Commits, open a PR, merge when CI is green.

## Scope boundary

CARCUX analyses **events and evidence**, never individuals or political opinions. The schema has no fields for political attributes or personal profiles. See `docs/` for the ethics and governance section of the specification.
