# CARCUX AI modules

Six modules, one per area in Spec v1.0 §6. **All six are built and deployed.** Two of them, `correlation` and `fusion`, are also the **research core** behind the Q1 paper, so they get original methods, baselines, ablations and robustness experiments. The other four are built with proven, existing tools so the effort stays where the paper needs it.

| # | Module | Area | Role | Paper |
|---|---|---|---|---|
| 1 | [`extraction/`](extraction/) | Bangla / Banglish / English event extraction | Engineered | Inputs to the core |
| 2 | [`media/`](media/) | Multimodal media understanding | Engineered | Inputs to the core |
| 3 | [`fusion/`](fusion/) | Evidence fusion under conflict | **Research core** | **Q1 paper** |
| 4 | [`correlation/`](correlation/) | Spatiotemporal event correlation | **Research core** | **Q1 paper** |
| 5 | [`integrity/`](integrity/) | Secure field systems (AI side) | Engineered | — |
| 6 | [`decision_support/`](decision_support/) | Human–AI decision support | Engineered, evaluated after deployment | Candidate 2nd paper |

## How they connect

```
 field reports ──┐                      ┌── integrity (5): is this report trustworthy?
 news / posts ───┼─> extraction (1) ────┤
 images / video ─┴─> media (2) ─────────┘
                         │  observations with claims, places, times, media hashes
                         ▼
                 correlation (4): which observations describe the same event?
                         │  event clusters
                         ▼
                 fusion (3): which sources are independent, where do they conflict,
                         │   how certain is the assessment?
                         │  events with relations, dependences, calibrated assessment
                         ▼
                 decision_support (6): priority, evidence-referenced summaries,
                                       assistant, human review
```

Every arrow carries **CARCUX-BD schema v1 records** (`data/schema/v1/`). That is the contract between modules: each one reads and writes the same event / observation / relation / dependence structures, so modules can be developed, tested and swapped independently.

## Rules

- **Scope discipline (Spec §6):** if an interesting research problem appears in modules 1, 2, 5 or 6 before the paper is submitted, write it up in `research/future-work/` and keep building with existing tools.
- **No module calls an LLM with privileged access.** External content is data, never instructions (Spec §9.3).
- **Each module ships with tests and an evaluation script** on CARCUX-BD before it is wired into the backend.
