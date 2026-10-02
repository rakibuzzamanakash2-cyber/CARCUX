# Contributing to CARCUX

## Workflow: GitHub flow

1. `main` is always in a working state. Never commit directly to it.
2. For every task, create a short-lived branch from the latest `main`:
   ```bash
   git switch main && git pull
   git switch -c feat/field-report-api
   ```
3. Commit small, focused changes (see message format below).
4. Push and open a Pull Request into `main`. Fill in the PR template.
5. Merge only when CI is green. Use **Squash and merge** so each PR becomes one clean commit on `main`.
6. Delete the branch after merging.

## Branch names

`<type>/<short-description>` in lowercase with hyphens.

| Prefix | Use for |
|---|---|
| `feat/` | New feature or capability |
| `fix/` | Bug fix |
| `data/` | Dataset schema, collection, annotation work |
| `exp/` | Research experiments, baselines, ablations |
| `docs/` | Documentation, specification, paper notes |
| `chore/` | Tooling, CI, dependencies, configuration |
| `refactor/` | Code restructuring without behaviour change |

Examples: `feat/backend-skeleton`, `data/schema-v1`, `exp/baseline-text-only`.

## Commit messages: Conventional Commits

```
<type>(<scope>): <summary in imperative mood, max ~72 chars>

<optional body: what and why, not how>
```

**Types:** `feat`, `fix`, `data`, `exp`, `docs`, `test`, `refactor`, `chore`, `ci`, `perf`

**Scopes:** `backend`, `frontend`, `fusion`, `extraction`, `media`, `dataset`, `research`, `deploy`, `security`, `docs`

Examples:
```
feat(backend): add field report submission endpoint
data(dataset): freeze event and observation schema v1
exp(fusion): add equal-weight fusion baseline
fix(extraction): handle Banglish place names without vowels
```

## Releases

Tag milestones on `main` with semantic versions, e.g. `v0.1.0` for Backend MVP. Dataset versions are tagged separately: `dataset-v0.1`.

## Never commit

- Secrets, API keys, `.env` files (use `.env.example` instead)
- Raw scraped copyrighted articles or media (store references and derived features)
- Personal data of any individual
- Large data or model files (keep them out of git; document where they live)

## Research reproducibility

Every experiment under `research/` records: config, random seeds, dataset version, code commit hash, and results. An experiment that cannot be reproduced does not go in the paper.
