# CARCUX-BD Annotation Guideline

**Version 0.1** · Schema v1 · Status: draft for the first annotation round

This guideline tells annotators how to turn news, posts, videos and field reports about Bangladesh disaster and disruption events into CARCUX-BD records. Two annotators following it should reach the same labels. When they don't, that is a signal to improve the guideline, not to argue.

---

## 1. What we are building

The unit of analysis is the **event and its evidence**, never a person.

| Record | One line per | File |
|---|---|---|
| Event | real-world event, reconstructed after the fact | `events.jsonl` |
| Source | outlet, account or field worker | `sources.jsonl` |
| Observation | article, post, video, image or field report | `observations.jsonl` |
| Relation | observation ↔ event: what the item says about the event | `relations.jsonl` |
| Dependence | observation → earlier observation it was copied from | `dependences.jsonl` |

Every file is checked with:

```bash
cd data/tools
python -m carcux_data.validate path/to/dataset
```

Run it before every commit. A dataset that fails validation is not merged.

---

## 2. Scope and privacy rules

**In scope:** three event families.

| Family | Types |
|---|---|
| `natural_calamity` | flood, flash_flood, waterlogging, cyclone, storm_surge, landslide, river_erosion, heavy_rainfall |
| `road_infrastructure` | road_blockage, road_accident, road_damage, bridge_damage, power_outage, gas_outage, water_outage, construction_closure |
| `urban_emergency` | fire, building_collapse, building_hazard, explosion |

**Out of scope:** political events as a category. A gathering that blocks a road may be recorded **only** as a `road_blockage`: place, time, duration, traffic impact. No organisers, no slogans, no sides, no political labels.

**Privacy rules (non-negotiable):**

1. **No names of private individuals.** Replace with `[PERSON]` in any stored text. Officials speaking in an official role may be named only if needed to identify the source, and preferably by role ("fire service spokesperson").
2. **No account handles.** Social sources get a salted hash in `account_ref`, never the handle. The validator rejects anything that is not a 64-character hash.
3. **No phone numbers or email addresses** anywhere in text, transcripts or OCR. The validator rejects them.
4. **No personal data about victims.** Aggregate counts only (`casualty_count`), never names, ages or photos of people.
5. **Neutral titles.** Factual and short: "Knee-deep waterlogging around Mirpur 10 after overnight rain". No blame, no adjectives like "shameful", no political framing.

**Copyright:** store the URL and short excerpts (≤ 300 characters), not full articles or media files. `content_policy` says what was stored:

| Value | Use when |
|---|---|
| `full` | Our own simulated items, or public-domain records |
| `excerpt` | Most real items: ≤ 300 characters of the original |
| `reference_only` | Only the URL and derived features are stored |

---

## 3. Events

### 3.1 What counts as one event

One event = **one type of thing happening at one place over one continuous period.**

- Waterlogging across Mirpur 10 from 07:30 to 14:00 → **one** event.
- Waterlogging in Mirpur and, separately, in Dhanmondi → **two** events (different places), even if the same rain caused both.
- A cyclone that floods a district and blocks three highways → **one** `cyclone` event plus child events (`flood`, `road_blockage` …) that point to it with `parent_event_id`.

**Rule of thumb:** if a responder would deal with it separately, it is a separate event.

### 3.2 Location

- `geometry`: a `Point` for a specific spot, a `Polygon` for an area. Coordinates are `[longitude, latitude]`. Note the order.
- `precision_m`: how far off the point could be. A named roundabout ≈ 150 m; a neighbourhood ≈ 600–1000 m; "Mirpur" ≈ 3000 m.
- `admin`: division and district are required; add upazila/thana, city corporation and locality when known.

### 3.3 Time

- All times in ISO 8601 **with offset**, normally `+06:00` (Dhaka). `2026-07-14T08:45:00+06:00`.
- `start`: when it began, as best established afterwards. `end`: when it was over (omit if unknown).
- `time_precision`: `minute` / `hour` / `day` / `unknown`: how exact `start` is.

### 3.4 Ground truth

Ground truth comes from **sources published after the event**: official statements, follow-up reporting, humanitarian situation reports. At least one source is required.

- `occurred`: `true` or `false`. **Rumoured events that did not happen are valuable; include them** with `occurred: false`.
- `facts`: the verified values: occurrence, magnitude, status at the end, cause, counts. These are what observations are judged against.
- If sources disagree after the event, record only what is well established and say so in `notes`.

### 3.5 Assessments (verification over time)

Each event gets gold assessments at **checkpoints after the first observation**: `T+1h`, `T+6h`, `T+24h` and/or `final`.

**At each checkpoint, use only observations published up to `as_of`.** The question is not "what really happened?" but "what should a careful analyst conclude *from the evidence available at that moment*?"

| Label | Meaning |
|---|---|
| `verified` | Independent, credible evidence establishes it happened as described |
| `partially_verified` | It happened, but key attributes (place, size, timing) are uncertain or disputed |
| `conflicting` | Credible evidence on both sides of whether it happened |
| `unverified` | Claims exist, but none independent or credible enough |
| `refuted` | Evidence establishes it did not happen (or not as claimed) |
| `insufficient_evidence` | Too little to judge |

**Independence matters.** Ten reposts of one post are one piece of evidence. Count only observations with no dependence on each other (Section 5).

Write a one- or two-sentence `rationale` naming the evidence that decided it.

---

## 4. Observations

### 4.1 Recording an item

| Field | Rule |
|---|---|
| `language` | `bn` Bangla script · `bn-Latn` Banglish ("Mirpur 10 e pani") · `en` English · `mixed` when two are substantially mixed |
| `published_at` | When it became public (or was submitted, for field reports) |
| `observed_at` | Only if the item says when the situation was seen ("at 8 am …") |
| `collected_at` | When we collected it |
| `location_mentions` | Every place mentioned, as written (`surface`) and resolved to coordinates. Mark GPS from field reports with `from_gps: true` |
| `media` | Perceptual hash (`phash`) of images/key frames, transcripts and OCR, never the file itself |

### 4.2 Claims

Claims are the checkable statements an item makes. One claim per attribute:

| Attribute | Value examples |
|---|---|
| `occurrence` | `true` / `false` (false = "this is not happening", "rumour") |
| `event_type` | from the type list in Section 2 |
| `location` | place as stated: "Mirpur 10 roundabout" |
| `start_time`, `end_time` | ISO time, if stated |
| `status` | `ongoing`, `worsening`, `improving`, `resolved` |
| `magnitude` | **Water depth:** `ankle-deep`, `knee-deep`, `waist-deep`, `chest-deep`, `above-head`. Others: short phrase ("two lanes closed") |
| `affected_count`, `casualty_count` | numbers, with `unit` ("households", "people") |
| `cause` | short phrase: "heavy overnight rainfall" |

Put the words that state the claim in `surface` (≤ 200 characters): "hatu pani" → `magnitude: knee-deep`.

Banglish depth words: *gorali/goral* ≈ ankle-deep · *hatu* ≈ knee-deep · *komor* ≈ waist-deep · *buk* ≈ chest-deep.

---

## 5. Relations: what does the item say about the event?

A relation labels the **stance of one observation toward one event**. One observation can relate to several events (a post about flooding that also mentions the road being blocked).

> **Stance is not truth.** Label what the item *says*, not whether it is right. A post claiming a fire that never happened still **supports** the (rumoured) fire event. Truth lives in the event's ground truth and assessments.

### 5.1 Decision procedure

Answer the questions in order and stop at the first "yes":

1. **Is it about a different event?** Wrong place, wrong day or wrong type → `unrelated`.
   *These matter: they are the hard negatives the model must learn to reject.*
2. **Does it make no checkable claim about this event?** Opinion, prayer, complaint, aftermath commentary → `related`.
3. **Does it deny the event, or call it false or a rumour?** → `contradicts`.
4. **Does it say the event happened, but get at least one attribute wrong compared with ground truth?** → `partially_supports`, and list every wrong attribute in `conflicts`.
5. Otherwise → `supports`.

### 5.2 When do attributes agree?

| Attribute | Agrees if |
|---|---|
| `location` | Same named locality, or within the event's `precision_m` |
| `start_time` | Within 1 hour (event precision `hour`) or same day (`day`) |
| `magnitude` | Same category. Knee-deep vs waist-deep **conflicts**. |
| counts | Within ±20 % of the ground-truth figure |
| `status` | Matches the true status **at the item's publication time** |

### 5.3 Stale items

Set `stale: true` when the item describes the event **as it was earlier** and was already out of date when published, e.g. "Mirpur 10 still underwater" posted after the water had gone. A stale item is usually `partially_supports` with `conflicts: [status]`.

### 5.4 Confidence

`1` unsure · `2` fairly sure · `3` certain. Use `1` freely. Honest low confidence is more useful than a confident guess, and it tells us where the guideline is unclear.

---

## 6. Dependences: who copied whom?

Mark an observation as dependent when it is **not independent evidence**:

| Type | When |
|---|---|
| `verbatim_copy` | Same text, re-published |
| `rewrite` | Same claims, reworded, no attribution |
| `repost` | Platform share or forward |
| `cites` | Explicitly says where it got the information ("according to …") |
| `same_media` | Reuses another item's photo or video (matching `phash`) |

Rules:

- Link each dependent item to the item it was **directly** copied from. Chains (A → B → C) form naturally.
- The origin must be published **before** the copy. The validator checks this.
- Record **how** you know in `evidence`: `text_overlap`, `attribution`, `platform_share`, `media_hash`, `timestamp_order`, `annotator_judgement`.
- If two items are similar but you cannot tell who copied whom, **do not** add a dependence; mention it in the relation's `note`.

---

## 7. Agreement and adjudication

1. Every relation and assessment is labelled independently by **two annotators** (`ANN-001`, `ANN-002` …). Annotators do not discuss items before both have finished.
2. Agreement is measured per label set with **Cohen's κ** (two annotators) or **Krippendorff's α** (more). Target: **κ ≥ 0.70** for relation labels before scaling up.
3. Disagreements are discussed and resolved into the `gold` field. If the disagreement came from an unclear rule, **update this guideline** and bump its version.
4. Annotators are identified only by code. The mapping to real people is kept outside the dataset.

---

## 8. Worked example

`data/samples/v1/example/` contains a small, **fully synthetic** dataset (all links point to `example.org`; it describes no real event). It shows:

| Case | Where |
|---|---|
| Field report in Banglish with GPS | `OBS-0000001` |
| Repost, so not independent evidence | `OBS-0000003` → `OBS-0000002` |
| News rewrite that gets the depth wrong (`partially_supports`, `conflicts: [magnitude]`) | `OBS-0000005` |
| Stale post reusing an old photo (`stale`, `same_media`) | `OBS-0000009` |
| Hard negative: road accident elsewhere (`unrelated`) | `OBS-0000010` |
| Rumoured fire that did not happen (`occurred: false`, final `refuted`) | `EVT-000003` |
| Child event linked to its cause (`parent_event_id`) | `EVT-000002` |
| Annotators disagreeing, resolved in `gold` | relations for `OBS-0000002`, `OBS-0000005` |

---

## 9. Changes from Spec v1.0

- **`DUPLICATES` moved out of relation labels** into its own file (`dependences.jsonl`). Copying is a link between two observations, not a stance toward an event, and the fusion model needs it as a graph.
- **`partially_supports` added** so attribute-level conflicts (wrong depth, wrong place) are separated from outright denial.
- **`refuted` added** to assessments. "We checked and it did not happen" was missing.
- **`stale` flag added** for outdated items.

---

## 10. Open questions for v0.2

- Exact checkpoint set: is `T+24h` needed for fast urban events?
- Magnitude vocabularies for non-water events (fire size, outage extent).
- How to annotate video segments when only part of a video is about the event.
- Whether to add a `retracted` dependence type for items later deleted or corrected.
