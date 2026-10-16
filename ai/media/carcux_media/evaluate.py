"""How well the media features work.

    python -m carcux_media.evaluate --hashes [FOLDER]   # reused photos: repost edits
    python -m carcux_media.evaluate --ocr               # text in images, CER
    python -m carcux_media.evaluate --asr FOLDER --model medium   # speech, WER
    python -m carcux_media.evaluate --classify FOLDER   # what images show, accuracy

**Reused photos.** Each photo in FOLDER is edited the way reposts are (resized,
recompressed, brightened, cropped, captioned, watermarked, mirrored, framed as a
screenshot, slightly rotated). A pair is positive when it is a photo and its own edit,
negative when the two come from different photos. Without FOLDER, the sample photographs that come
with scikit-image, scikit-learn and matplotlib are used if installed. Recall and false
matches are reported at each threshold.

**OCR.** Lines in Bangla, English and Banglish (Romanized), as on signboards, tickers
and screenshots, are drawn in several fonts and degraded (blur, recompression, low
contrast, small text), then read back; the score is the character error rate.

**ASR.** FOLDER holds audio or video files, each with a .txt of the same name holding
what is said; the score is the word and character error rate.

**Classify.** FOLDER holds one sub-folder per label (flooding, fire, collapse, …).
"""

import argparse
import io
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from carcux_media import ocr
from carcux_media.hashing import SAME_IMAGE_BITS, distance, hamming, hashes

PHOTO_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
# Sample photographs (not drawings, charts or test patterns) that come with common
# Python packages, for a run without a folder of your own.
SAMPLE_PHOTOS = [
    "skimage/data/astronaut.png", "skimage/data/camera.png", "skimage/data/chelsea.png",
    "skimage/data/coffee.png", "skimage/data/coins.png", "skimage/data/motorcycle_left.png",
    "skimage/data/motorcycle_right.png", "skimage/data/rocket.jpg",
    "skimage/data/hubble_deep_field.jpg",
    "skimage/data/retina.jpg", "skimage/data/grass.png", "skimage/data/gravel.png",
    "skimage/data/brick.png", "skimage/data/moon.png", "skimage/data/cell.png",
    "skimage/data/clock_motion.png", "skimage/data/horse.png", "skimage/data/page.png",
    "skimage/data/text.png", "skimage/data/ihc.png", "sklearn/datasets/images/china.jpg",
    "sklearn/datasets/images/flower.jpg", "matplotlib/mpl-data/sample_data/grace_hopper.jpg",
]  # fmt: skip


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf", "LiberationSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _jpeg(im: Image.Image, quality: int) -> Image.Image:
    buf = io.BytesIO()
    im.convert("RGB").save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    return Image.open(buf).copy()


def _crop(im: Image.Image, share: float) -> Image.Image:
    w, h = im.size
    dx, dy = int(w * share / 2), int(h * share / 2)
    return im.crop((dx, dy, w - dx, h - dy))


def _caption(im: Image.Image) -> Image.Image:
    """A news-style caption bar over the bottom of the photo."""
    out = im.convert("RGB").copy()
    w, h = out.size
    d = ImageDraw.Draw(out)
    d.rectangle((0, int(h * 0.85), w, h), fill=(180, 0, 0))
    d.text((10, int(h * 0.87)), "BREAKING: SHARE NOW", fill="white", font=_font(max(h // 16, 10)))
    return out


def _watermark(im: Image.Image) -> Image.Image:
    out = im.convert("RGB").copy()
    w, h = out.size
    ImageDraw.Draw(out).text(
        (w // 20, h // 20), "@page", fill="white", font=_font(max(h // 12, 10))
    )
    return out


def _screenshot(im: Image.Image) -> Image.Image:
    """The photo inside a white post frame with a header, as a screenshot shows it."""
    w, h = im.size
    frame = Image.new("RGB", (int(w * 1.1), int(h * 1.35)), "white")
    ImageDraw.Draw(frame).text(
        (10, 10), "Some Page · 2h", fill="black", font=_font(max(h // 18, 10))
    )
    frame.paste(im.convert("RGB"), (int(w * 0.05), int(h * 0.2)))
    return frame


EDITS = {
    "resized to half": lambda im: im.resize((im.width // 2, im.height // 2)),
    "recompressed (JPEG 25)": lambda im: _jpeg(im, 25),
    "brightened 25%": lambda im: ImageEnhance.Brightness(im.convert("RGB")).enhance(1.25),
    "less contrast": lambda im: ImageEnhance.Contrast(im.convert("RGB")).enhance(0.7),
    "cropped 10%": lambda im: _crop(im, 0.10),
    "cropped 25%": lambda im: _crop(im, 0.25),
    "caption bar": _caption,
    "watermark": _watermark,
    "mirrored": ImageOps.mirror,
    "rotated 3°": lambda im: im.convert("RGB").rotate(3, expand=False, fillcolor="black"),
    "screenshot frame": _screenshot,
}


def _photos(folder: str | None) -> list[tuple[str, Image.Image]]:
    if folder:
        files = sorted(f for f in Path(folder).rglob("*") if f.suffix.lower() in PHOTO_SUFFIXES)
    else:
        roots = [Path(p) for p in sys.path if p and Path(p).is_dir()]
        files = []
        for rel in SAMPLE_PHOTOS:
            found = next((r / rel for r in roots if (r / rel).is_file()), None)
            if found:
                files.append(found)
    out = []
    for f in files:
        with Image.open(f) as im:
            out.append((f.name, im.convert("RGB")))
    return out


def _distance(method: str, a: dict, b: dict) -> int:
    return {
        "dhash": lambda: hamming(a["dhash"], b["dhash"]),
        "dhash+mirror": lambda: distance(a, b, "dhash"),
        "phash+mirror": lambda: distance(a, b, "phash"),
        "either (used)": lambda: distance(a, b),
    }[method]()


def evaluate_hashes(folder: str | None = None) -> dict:
    """Recall on each photo's edits, and false matches between different photos, at each
    threshold (bits apart). Pairs of different photos that show the same scene at the
    same moment (a stereo pair) are counted separately: no hash can tell them apart."""
    photos = _photos(folder)
    if len(photos) < 4:
        raise SystemExit("need at least 4 photos: give a folder, or install scikit-image")
    names = [n for n, _ in photos]
    original = [hashes(im) for _, im in photos]
    edited = [{name: hashes(fn(im)) for name, fn in EDITS.items()} for _, im in photos]
    scene = {frozenset({"motorcycle_left.png", "motorcycle_right.png"})}  # same scene, two cameras
    result: dict = {"photos": len(photos), "edits": list(EDITS), "methods": {}}
    for method in ("dhash", "dhash+mirror", "phash+mirror", "either (used)"):
        pos = [(_distance(method, original[i], edited[i][e]), e)
               for i in range(len(photos)) for e in EDITS]  # fmt: skip
        neg, same_scene = [], []
        for i in range(len(photos)):
            for j in range(len(photos)):
                if i == j:
                    continue
                bucket = same_scene if frozenset({names[i], names[j]}) in scene else neg
                for other in [original[j], *edited[j].values()]:
                    bucket.append(_distance(method, original[i], other))
        curve = []
        for t in range(6, 23, 2):
            tp = sum(d <= t for d, _ in pos)
            fp = sum(d <= t for d in neg)
            curve.append(
                {
                    "threshold": t,
                    "recall": tp / len(pos),
                    "false_matches": fp,
                    "precision": tp / (tp + fp) if tp + fp else None,
                    "same_scene_matched": sum(d <= t for d in same_scene),
                }
            )
        at = SAME_IMAGE_BITS
        result["methods"][method] = {
            "positive_pairs": len(pos),
            "negative_pairs": len(neg),
            "same_scene_pairs": len(same_scene),
            "curve": curve,
            "recall_per_edit": {
                e: sum(d <= at for d, n in pos if n == e) / len(photos) for e in EDITS
            },
        }
    return result


# --- OCR -------------------------------------------------------------------------------

OCR_LINES = {
    "bn": [
        "মিরপুর ১০ নম্বরে হাঁটুসমান পানি", "ফেনীতে বন্যায় মৃতের সংখ্যা বেড়ে ২৩",
        "বেইলি রোডে আগুনে নিহত ৪৬", "সড়ক বন্ধ, বিকল্প পথ ব্যবহার করুন",
        "ঘূর্ণিঝড়ের কারণে ৭ নম্বর বিপদ সংকেত", "আশ্রয়কেন্দ্রে যান, নিরাপদে থাকুন",
        "ভূমিকম্পে ভবন হেলে পড়েছে", "জরুরি প্রয়োজনে ৯৯৯ নম্বরে ফোন করুন",
        "নদীর পানি বিপদসীমার উপরে", "বিদ্যুৎ সরবরাহ বন্ধ থাকবে",
    ],
    "en": [
        "Road closed at Farmgate", "Flood water rising in Feni", "Fire at Bailey Road building",
        "Death toll rises to 71", "Signal 7 for Chattogram port", "Use alternative routes",
        "Rescue boats needed in Noakhali", "Power cut until 6 pm",
    ],
    "bn-Latn": [
        "Mirpur 10 e hatu pani", "Feni te bonna, sahajjo dorkar", "rasta bondho, onno rasta nin",
        "agun lagse, fire service ashche", "gujob e kan diben na",
    ],
}  # fmt: skip
OCR_FONTS = {
    "bn": ["NotoSansBengali-Regular.ttf", "Muktibold.ttf", "Nirmala.ttf", "Vrinda.ttf"],
    "latin": ["DejaVuSans.ttf", "LiberationSerif-Regular.ttf", "arial.ttf", "times.ttf"],
}
OCR_FONT_DIRS = ["/usr/share/fonts", "C:/Windows/Fonts", "/Library/Fonts", "/System/Library/Fonts"]


def _find_fonts(names: list[str]) -> list[Path]:
    found = []
    for name in names:
        for root in OCR_FONT_DIRS:
            hit = next(Path(root).rglob(name), None) if Path(root).is_dir() else None
            if hit:
                found.append(hit)
                break
    return found


def _render(text: str, font: Path, size: int) -> Image.Image:
    f = ImageFont.truetype(str(font), size)
    left, top, right, bottom = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), text, font=f)
    im = Image.new("RGB", (right - left + 40, bottom - top + 30), "white")
    ImageDraw.Draw(im).text((20 - left, 15 - top), text, font=f, fill="black")
    return im


DEGRADE = {
    "clean": lambda im: im,
    "blurred": lambda im: im.filter(ImageFilter.GaussianBlur(1.2)),
    "recompressed": lambda im: _jpeg(im, 20),
    "low contrast": lambda im: ImageEnhance.Contrast(im).enhance(0.35),
    "small text": lambda im: im.resize((max(im.width // 2, 1), max(im.height // 2, 1))),
}


def evaluate_ocr() -> dict:
    from carcux_media.asr import char_error_rate

    if not ocr.available():
        raise SystemExit("tesseract is not installed")
    fonts = {"bn": _find_fonts(OCR_FONTS["bn"]), "latin": _find_fonts(OCR_FONTS["latin"])}
    rows = []
    for lang, lines in OCR_LINES.items():
        for font in fonts["bn" if lang == "bn" else "latin"]:
            for line in lines:
                base = _render(line, font, 40)
                for name, fn in DEGRADE.items():
                    got = ocr.read_text(fn(base), psm=7).text
                    rows.append((lang, font.name, name, char_error_rate(line, got)))

    def mean(xs):
        return sum(xs) / len(xs) if xs else None

    by_lang = {lang: mean([c for lg, _, _, c in rows if lg == lang]) for lang in OCR_LINES}
    by_cond = {
        lang: {n: mean([c for lg, _, d, c in rows if lg == lang and d == n]) for n in DEGRADE}
        for lang in OCR_LINES
    }
    return {"lines": len(rows), "fonts": {k: [f.name for f in v] for k, v in fonts.items()},
            "cer": by_lang, "cer_by_condition": by_cond}  # fmt: skip


# --- ASR and classification on your own data -------------------------------------------


def evaluate_asr(folder: str, model: str) -> dict:
    from carcux_media.asr import WhisperASR, char_error_rate, word_error_rate

    asr = WhisperASR(model)
    rows = []
    for f in sorted(Path(folder).iterdir()):
        ref = f.with_suffix(".txt")
        if f.suffix.lower() == ".txt" or not ref.exists():
            continue
        t = asr.transcribe(f)
        truth = ref.read_text("utf-8").strip()
        wer, cer = word_error_rate(truth, t.text), char_error_rate(truth, t.text)
        rows.append({"file": f.name, "language": t.language, "wer": wer, "cer": cer})
    n = len(rows)
    return {"files": n, "model": model,
            "wer": sum(r["wer"] for r in rows) / n if n else None,
            "cer": sum(r["cer"] for r in rows) / n if n else None, "rows": rows}  # fmt: skip


def _f(x) -> str:
    return "-" if x is None else f"{x:.3f}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m carcux_media.evaluate")
    ap.add_argument("--hashes", nargs="?", const="", metavar="FOLDER")
    ap.add_argument("--ocr", action="store_true")
    ap.add_argument("--asr", metavar="FOLDER")
    ap.add_argument("--model", default="small")
    ap.add_argument("--classify", metavar="FOLDER")
    ap.add_argument("--json", help="also write the results here")
    args = ap.parse_args(argv)
    out: dict = {}
    if args.hashes is not None:
        r = out["hashes"] = evaluate_hashes(args.hashes or None)
        print(f"Reused photos: {r['photos']} photos × {len(r['edits'])} repost edits")
        for m, v in r["methods"].items():
            print(
                f"  {m}: {v['positive_pairs']} same-photo pairs, {v['negative_pairs']} "
                f"different-photo pairs, {v['same_scene_pairs']} same-scene pairs"
            )
            for c in v["curve"]:
                print(
                    f"    ≤{c['threshold']:>2} bits  recall {c['recall']:.3f}  precision "
                    f"{_f(c['precision'])}  false matches {c['false_matches']:>4}  "
                    f"same scene matched {c['same_scene_matched']}"
                )
        print(f"  recall per edit at ≤{SAME_IMAGE_BITS} bits (either hash, as used):")
        for name, rec in r["methods"]["either (used)"]["recall_per_edit"].items():
            print(f"    {name:<24} {rec:.2f}")
    if args.ocr:
        r = out["ocr"] = evaluate_ocr()
        print(f"OCR: {r['lines']} rendered lines; fonts {r['fonts']}")
        for lang, cer in r["cer"].items():
            conds = "  ".join(f"{n} {_f(c)}" for n, c in r["cer_by_condition"][lang].items())
            print(f"  {lang:<8} CER {_f(cer)}   ({conds})")
    if args.asr:
        r = out["asr"] = evaluate_asr(args.asr, args.model)
        print(f"ASR ({r['model']}): {r['files']} files, WER {_f(r['wer'])}, CER {_f(r['cer'])}")
    if args.classify:
        from carcux_media.classify import ClipClassifier, evaluate_folder

        r = out["classify"] = evaluate_folder(ClipClassifier(), args.classify)
        print(f"Classify: {r['images']} images, accuracy {_f(r['accuracy'])}")
    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=2, ensure_ascii=False), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
