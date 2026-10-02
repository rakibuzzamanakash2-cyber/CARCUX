# CARCUX-BD dataset

Event–evidence dataset for disaster and disruption events in Bangladesh. The unit of analysis is **event + evidence**, never a person.

| Path | Contents |
|---|---|
| `schema/v1/` | JSON Schemas: `event`, `source`, `observation`, `relation`, `dependence` (+ shared `common`) |
| `annotation/guideline.md` | How to annotate: the rules every annotator follows |
| `samples/v1/example/` | Small **synthetic** worked example covering every label and dependence type |
| `tools/` | `carcux_data` package: dataset validator and its tests |

## Data model

```
Source ──< Observation >──── Relation ────< Event
              │   (stance: supports / partially_supports /       │
              │    contradicts / related / unrelated)            │ parent_event_id
              │                                                  ▼
              └── Dependence ──> earlier Observation           Event
                  (verbatim_copy / rewrite / repost /
                   cites / same_media)
```

- **Relations** say what an item claims about an event. Stance, not truth.
- **Dependences** say which items are copies, so 100 reposts count as one piece of evidence.
- **Events** carry the ground truth and gold **assessments** at checkpoints (T+1h, T+6h, …), which is what the fusion model is evaluated against.

## Validate a dataset

```bash
cd data/tools
pip install -e ".[dev]"
python -m carcux_data.validate ../samples/v1/example
pytest
```

The validator checks every record against its schema, then cross-record rules: unique ids, references exist, type matches family, a copy is published after its original, no dependence or parent cycles, no phone numbers or emails in text, simulated field reports come from simulated field sources.

## Never commit

Raw scraped articles or media, account handles, names of private individuals, contact details. See the guideline's privacy rules.
