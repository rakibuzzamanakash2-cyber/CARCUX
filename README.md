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
| `ai/` | Six AI modules, one per Spec §6 area. `correlation/` and `fusion/` are the research core; see [`ai/README.md`](ai/README.md) |
| `data/` | Dataset schema, annotation guideline, samples, dataset card (CARCUX-BD) |
| `research/` | Literature notes, baselines, experiments, ablations, robustness, results |
| `deployment/` | Docker, Compose, deployment configuration |
| `docs/` | Specification, architecture, security, threat model, API |
| `tests/` | Cross-component and integration tests |

## Tracks

Work runs in three parallel tracks — **Code**, **Dataset**, **Paper** — as described in the Spec v1.0. Use the matching label on every issue and PR.

## Getting started

Run everything (database, backend, frontend) with Docker:

```bash
docker compose -f deployment/docker-compose.yml up --build
docker compose -f deployment/docker-compose.yml exec backend python -m app.cli create-admin --email you@office.local --name "Your Name"
```

Then open http://localhost:3000. Details: `backend/README.md`, `frontend/README.md`.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) before your first commit. Short version: branch from `main`, use Conventional Commits, open a PR, merge when CI is green.

## Scope boundary

CARCUX analyses **events and evidence**, never individuals or political opinions. The schema has no fields for political attributes or personal profiles. See `docs/` for the ethics and governance section of the specification.
