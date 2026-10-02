# 1 · Extraction: Bangla / Banglish / English

**Role:** engineered with existing models · **Spec:** §6, §9.2 · **Status:** not started

Turns raw text (articles, posts, field reports, transcripts) into structured observations.

## In → out

| In | Out (schema v1) |
|---|---|
| Raw text + metadata | `observation.language` (`bn` / `bn-Latn` / `en` / `mixed`) |
| | `observation.claims`: occurrence, event_type, magnitude, status, counts, cause |
| | `observation.location_mentions`: place names resolved to coordinates (geocoding) |
| | times normalised to ISO 8601 with offset |

## Planned components

1. **Language identification**, including Banglish (Romanized Bangla) and code-mixed text
2. **Event type and claim extraction:** fine-tuned multilingual encoder (BanglaBERT / XLM-R) plus an LLM extractor as a strong baseline
3. **Place-name extraction and geocoding** against a Bangladesh gazetteer (division → district → upazila/thana → locality)
4. **Time normalisation:** "ajke shokale", "gotokal raat theke" → ISO times

## Done when

Claim extraction macro-F1 and geocoding accuracy are reported on CARCUX-BD, and outputs pass the dataset validator.
