# 2 · Media: images, video, audio

**Role:** engineered with existing models · **Spec:** §6, §9.2 · **Status:** not started

Turns attached media into features the rest of the pipeline can use. Media files are never stored in the dataset, only derived features.

## In → out

| In | Out (schema v1) |
|---|---|
| Image | `media[].phash` (perceptual hash), `media[].ocr_text` |
| Video | key-frame `phash`es, `transcript` (ASR), `ocr_text`, `duration_s` |
| Audio / voice note | `transcript` (ASR, Bangla + English) |

## Planned components

1. **Perceptual hashing** of images and key frames: detects reused photos (the `same_media` dependence) and old images reposted as new
2. **ASR** with a Whisper-family model, Bangla and English
3. **OCR** for text in images (signboards, screenshots, news tickers)
4. **Image embeddings** (CLIP-style) for "does this image show flooding / fire / a blocked road?"

**Out of scope until after the paper:** deepfake and manipulation detection as research.

## Done when

Reused-media detection precision/recall and ASR word error rate are reported on CARCUX-BD samples.
