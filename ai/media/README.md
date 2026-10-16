# 2 · Media: images, video, audio

**Role:** engineered with existing models · **Spec:** §6, §9.2 · **Status:** perceptual hashing (photos and video frames), Bangla and English OCR, video and audio probing, speech recognition (Whisper) and image classification (CLIP) built, with an evaluation for each. Hashing and OCR are measured here; Whisper and CLIP run where there is a GPU and are measured on your own files. Not yet wired into the backend.

Turns attached media into features the rest of the pipeline can use. **Media files are never stored in the dataset, only derived features** (`media[]`: `kind`, `phash`, `ocr_text`, `transcript`, `duration_s`).

## In → out

| In | Out | How |
|---|---|---|
| Image | `phash`, `ocr_text`; what it shows (hint) | `hashing.py` (dHash and pHash, also mirrored), `ocr.py` (Tesseract, Bangla + English), `classify.py` (CLIP zero-shot) |
| Video | `duration_s`, frame hashes, `transcript` | `video.py` (ffmpeg: a frame every 2 s), `asr.py` (Whisper) |
| Voice note / audio | `duration_s`, `transcript` | `video.py` (ffprobe), `asr.py` |

```bash
python -m carcux_media.extract photo.jpg clip.mp4 note.ogg                 # hashes, OCR, durations
python -m carcux_media.extract clip.mp4 note.ogg --asr medium --classify    # with the models
```

## Install

```bash
pip install -e ".[dev]"            # Pillow and numpy only
pip install -e ".[asr]"            # + Whisper (faster-whisper)
pip install -e ".[vision]"         # + CLIP (open_clip, torch)
```

Programs: **Tesseract** with Bangla (Ubuntu: `apt install tesseract-ocr tesseract-ocr-ben`; Windows: the UB Mannheim installer, with "Bengali" ticked under additional languages) and **ffmpeg**. Whisper and CLIP download their weights on first use (Whisper "small" about 0.5 GB, "medium" about 1.5 GB; CLIP ViT-B-32 about 0.6 GB) and run on a GPU when CUDA is there. Nothing sends media anywhere: keep real CARCUX recordings and photos on your own machine.

## Reused photos (`hashing.py`)

Two 64-bit hashes, each also of the mirror image: **dHash**, the difference hash the backend already stores for field report photos (so hashes compare directly), and **pHash**, a DCT hash. Two images are the same picture when either hash, as is or mirrored, is at most **10 bits** apart (`SAME_IMAGE_BITS`). Video clips are compared frame by frame (`video.shared_frames`: the share of the shorter clip's frames found in the other).

### Results (17 October 2026; 23 sample photographs, not CARCUX photos)

`python -m carcux_media.evaluate --hashes`: each photo is edited the way reposts are (11 edits), giving 253 same-photo pairs and 6,048 pairs of different photos. Two of the photos are a stereo pair (the same scene from two cameras at the same moment), counted apart: no hash can tell them apart, and in practice they would be one event's photos anyway.

| Rule | Recall | False matches (of 6,048) | Precision |
|---|---|---|---|
| dHash ≤ 14 | 0.731 | 0 | 1.000 |
| dHash + mirror ≤ 10 | 0.775 | 0 | 1.000 |
| pHash + mirror ≤ 12 | 0.711 | 0 | 1.000 |
| **Either hash + mirror ≤ 10 (used)** | **0.798** | **0** | **1.000** |
| Either hash + mirror ≤ 12 | 0.810 | 1 | 0.995 |

Recall per edit at the rule used: resized, recompressed (JPEG 25), brightened, less contrast, caption bar, watermark, mirrored **1.00**; rotated 3° 0.91; cropped 10% 0.74; **cropped 25% 0.09; framed inside a screenshot 0.04**. Heavy crops and screenshots of a post are where reposts escape; catching them needs local features (keypoint matching), a next step.

**How this was reached, honestly.** The first two runs chose the threshold on half the photos and scored the other half, by F1 and then by "highest recall with precision ≥ 0.95". With 11–12 photos per half this was too noisy (thresholds of 20–22 bits, test precision 0.55–0.91), and a first conclusion that dHash is much noisier than pHash came from those thresholds and was wrong. The table above is the full precision–recall curve on all 23 photos, and the rule (either hash, 10 bits) was chosen on it, so the figures are optimistic. They must be checked on real CARCUX photos: `python -m carcux_media.evaluate --hashes FOLDER` runs the same edits on any folder of photos.

## Text in images (`ocr.py`)

Tesseract with Bangla and English together (`ben+eng`). Small images (under 1000 px on the longer side) are doubled; larger ones are read as they are. Words below 40% confidence are dropped, so the text is short rather than wrong; a blank image gives no text.

### Results (17 October 2026; rendered lines, not photographs)

`python -m carcux_media.evaluate --ocr`: 23 lines like signboards, tickers and screenshots (10 Bangla, 8 English, 5 Banglish), in two fonts each, clean and degraded (blur, JPEG 20, low contrast, half size): 230 images. Character error rate:

| | Bangla | English | Banglish |
|---|---|---|---|
| First run | 0.085 | 0.057 | 0.131 |
| **After fixing enlargement** | **0.063** | **0.020** | **0.051** |

The first run enlarged every image to 900 px high, which blew single lines up to letters 300 px tall; Tesseract reads best at about 30 px a line, so clean text scored worse than blurred. Enlarging only small images fixed it; nothing else was changed. Typical Bangla errors are dropped marks (চন্দ্রবিন্দু ঁ: হাঁটু read as হাটু). **Caveat:** rendered text is much easier than photos of signs, at an angle, in poor light; measure on real photos with their text typed out.

## Speech (`asr.py`) and what images show (`classify.py`)

- **Whisper** through faster-whisper, Bangla and English, voice activity filtering on. `evaluate --asr FOLDER --model medium`: FOLDER holds recordings, each with a `.txt` of what is said; reports word and character error rates. "medium" is noticeably better on Bangla than "small".
- **CLIP** zero-shot against short descriptions of flooding, fire, collapse, a blocked road, an accident, a landslide, a crowd, or nothing in particular, mapped to CARCUX event types. A hint for analysts, never a decision. `evaluate --classify FOLDER`: FOLDER holds one sub-folder per label; reports accuracy and a confusion table.

Neither model can be downloaded in the development container, so neither is measured yet; tests use stand-ins (`FakeASR`, `FakeClassifier`). Run both on your PC's GPU with photos and voice notes you are allowed to use.

## Run the checks

```bash
pytest -q && ruff check . && ruff format --check .
python -m carcux_media.evaluate --hashes --ocr --json media.json
```

On Windows, if scikit-image is not installed, give `--hashes` a folder of your own photos.

## Next

1. **Into the product:** OCR and pHash for field report photos at submission (Tesseract in the backend image), shown with the report and exported as `ocr_text`; reused-photo checks across reports and signals with the rule above.
2. Real measurements: CARCUX photos for hashing and OCR, voice notes for Whisper, labelled photos for CLIP.
3. Heavy crops and screenshots: keypoint matching (ORB) as a second stage when hashes miss.
4. **Out of scope until after the paper:** deepfake and manipulation detection as research.
