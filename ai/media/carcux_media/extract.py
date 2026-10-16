"""Media features for one or more files, as the dataset's `media[]` items.

    python -m carcux_media.extract photo.jpg clip.mp4 voice.ogg
    python -m carcux_media.extract clip.mp4 --asr medium --classify     # with the models

Images: hash, and OCR text when Tesseract is installed. Video: duration, the first
frame's hash (all frames' hashes under `extra`), and the transcript with --asr. Audio:
duration and the transcript with --asr. Never the file itself.
"""

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

from carcux_media import asr as asr_mod
from carcux_media import ocr, video
from carcux_media.hashing import hashes

IMAGE = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
VIDEO = {".mp4", ".mov", ".mkv", ".webm", ".3gp", ".avi"}
AUDIO = {".mp3", ".ogg", ".opus", ".m4a", ".wav", ".aac", ".amr"}


def features(path: Path, recogniser=None, classifier=None, with_ocr: bool = True) -> dict:
    """One `media[]` item (kind, phash, ocr_text, transcript, duration_s) plus `extra`
    (all hashes, OCR confidence, transcript language, what the image shows), which the
    dataset leaves out."""
    suffix = path.suffix.lower()
    extra: dict = {}
    if suffix in IMAGE:
        with Image.open(path) as im:
            im.load()
            h = hashes(im)
            item = {"kind": "image", "phash": h["dhash"]}
            extra["hashes"] = h
            if with_ocr and ocr.available():
                r = ocr.read_text(im)
                if r.text:
                    item["ocr_text"] = r.text
                    extra["ocr_confidence"] = r.confidence
            if classifier is not None:
                extra["shows"] = [g.__dict__ for g in classifier.classify(im)[:3]]
    elif suffix in VIDEO | AUDIO:
        info = video.probe(path)
        item = {"kind": "video" if info["video"] else "audio", "duration_s": info["duration_s"]}
        if info["video"]:
            hs = video.frame_hashes(path)
            if hs:
                item["phash"] = hs[0]["dhash"]
                extra["frame_hashes"] = hs
        if recogniser is not None and info["audio"]:
            t = recogniser.transcribe(path)
            if t.text:
                item["transcript"] = t.text
                extra["transcript_language"] = t.language
    else:
        raise ValueError(f"{path.name}: not an image, video or audio file")
    return {**item, "extra": extra}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m carcux_media.extract")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--asr", metavar="MODEL", help="transcribe with Whisper (e.g. small, medium)")
    ap.add_argument("--classify", action="store_true", help="say what images show (CLIP)")
    ap.add_argument("--no-ocr", action="store_true")
    args = ap.parse_args(argv)
    recogniser = asr_mod.WhisperASR(args.asr) if args.asr else None
    classifier = None
    if args.classify:
        from carcux_media.classify import ClipClassifier

        classifier = ClipClassifier()
    out = [{"file": f, **features(Path(f), recogniser, classifier, not args.no_ocr)}
           for f in args.files]  # fmt: skip
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
