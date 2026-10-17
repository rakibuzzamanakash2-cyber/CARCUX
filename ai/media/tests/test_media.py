"""Media features: hashes for reused photos and video frames, OCR, transcripts, what an
image shows, and the extract command. OCR and video tests run when tesseract and ffmpeg
are installed; the Whisper and CLIP models are stood in for by fakes."""

import json
import shutil
import subprocess

import pytest
from PIL import Image, ImageDraw, ImageFont, ImageOps

from carcux_media import extract, ocr, video
from carcux_media.asr import FakeASR, char_error_rate, word_error_rate
from carcux_media.classify import FakeClassifier, evaluate_folder
from carcux_media.evaluate import EDITS
from carcux_media.hashing import dhash, distance, hashes, same_image


def scene(seed: int, size=(640, 480)) -> Image.Image:
    """A photo-like test image: gradients and shapes that differ by seed."""
    import random

    rng = random.Random(seed)  # noqa: S311 (test pictures, not secrets)
    im = Image.new("RGB", size)
    d = ImageDraw.Draw(im)
    for y in range(size[1]):
        c = int(255 * y / size[1])
        d.line([(0, y), (size[0], y)], fill=(c, rng.randint(0, 255) // 3 + c // 2, 255 - c))
    for _ in range(12):
        x, y = rng.randint(0, size[0]), rng.randint(0, size[1])
        r = rng.randint(20, 120)
        d.ellipse((x - r, y - r, x + r, y + r), fill=tuple(rng.randint(0, 255) for _ in range(3)))
    return im


# --- Hashes ----------------------------------------------------------------------------


def test_dhash_is_the_backends():
    # backend/app/services/media.py computes the same 64-bit difference hash.
    im = scene(1)
    small = im.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    px = list(small.tobytes())
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (1 if px[row * 9 + col] > px[row * 9 + col + 1] else 0)
    assert dhash(im) == f"{bits:016x}" and len(dhash(im)) == 16


@pytest.mark.parametrize(
    "edit", ["resized to half", "recompressed (JPEG 25)", "brightened 25%", "caption bar",
             "watermark", "mirrored"],
)  # fmt: skip
def test_a_repost_is_the_same_picture(edit):
    im = scene(2)
    assert same_image(hashes(im), hashes(EDITS[edit](im)))


def test_different_pictures_are_not_the_same():
    a, b = hashes(scene(3)), hashes(scene(4))
    assert not same_image(a, b)
    assert distance(a, b) > 10


# --- OCR -------------------------------------------------------------------------------


def _bangla_font():
    for path in ("/usr/share/fonts/truetype/noto/NotoSansBengali-Regular.ttf",
                 "C:/Windows/Fonts/Nirmala.ttf"):  # fmt: skip
        try:
            return ImageFont.truetype(path, 44)
        except OSError:
            continue
    return None


@pytest.mark.skipif(not ocr.available(), reason="tesseract is not installed")
def test_ocr_reads_bangla_and_english():
    font = _bangla_font()
    if font is None:
        pytest.skip("no Bangla font")
    im = Image.new("RGB", (900, 170), "white")
    d = ImageDraw.Draw(im)
    d.text((20, 20), "সড়ক বন্ধ, বিকল্প পথ", font=font, fill="black")
    d.text((20, 100), "Road closed at Farmgate", font=ImageFont.truetype("DejaVuSans.ttf", 36),
           fill="black")  # fmt: skip
    r = ocr.read_text(im)
    assert "Road closed at Farmgate" in r.text
    assert char_error_rate("সড়ক বন্ধ, বিকল্প পথ", r.text.splitlines()[0]) < 0.25
    assert r.confidence and r.confidence > 50


@pytest.mark.skipif(not ocr.available(), reason="tesseract is not installed")
def test_ocr_of_a_blank_image_is_empty_not_invented():
    assert ocr.read_text(Image.new("RGB", (400, 300), "white")).text == ""


# --- Video -----------------------------------------------------------------------------


def _clip(tmp_path, name, seeds, every=1):
    for i, s in enumerate(seeds):
        scene(s, (320, 240)).save(tmp_path / f"{name}{i:02d}.png")
    out = tmp_path / f"{name}.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-framerate", f"1/{every}", "-i",
         str(tmp_path / f"{name}%02d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-r", "10", str(out)],
        check=True,
    )  # fmt: skip
    return out


@pytest.mark.skipif(not video.available(), reason="ffmpeg is not installed")
def test_a_reencoded_clip_shares_its_frames(tmp_path):
    a = _clip(tmp_path, "a", [10, 11, 12, 13], every=2)
    small = tmp_path / "a_small.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(a), "-vf", "scale=160:-2",
                    "-crf", "35", str(small)], check=True)  # fmt: skip
    other = _clip(tmp_path, "b", [20, 21, 22, 23], every=2)
    info = video.probe(a)
    assert info["video"] and not info["audio"] and 7 <= info["duration_s"] <= 9
    ha, hs, ho = (video.frame_hashes(p) for p in (a, small, other))
    assert video.shared_frames(ha, hs) >= 0.75
    assert video.shared_frames(ha, ho) == 0.0


# --- Speech and what images show (models stood in for) -------------------------------


def test_error_rates():
    assert word_error_rate("pani barche feni te", "pani barche feni te") == 0
    assert word_error_rate("pani barche feni te", "pani komche feni te") == 0.25
    assert char_error_rate("আগুন", "আগুন") == 0 and char_error_rate("abcd", "abed") == 0.25


def test_fake_asr_and_fake_classifier(tmp_path):
    t = FakeASR({"note.ogg": "Mirpur e pani"}).transcribe(tmp_path / "note.ogg")
    assert (t.text, t.language) == ("Mirpur e pani", "bn")
    for label, size in (("fire", (100, 80)), ("flooding", (90, 90))):
        (tmp_path / label).mkdir()
        Image.new("RGB", size).save(tmp_path / label / "a.png")
    clf = FakeClassifier({(100, 80): "fire", (90, 90): "fire"})
    top = clf.classify(Image.new("RGB", (100, 80)))[0]
    assert top.label == "fire" and top.event_types == ("fire",)
    r = evaluate_folder(clf, tmp_path)
    assert r["images"] == 2 and r["accuracy"] == 0.5
    assert r["confusion"]["flooding"] == {"fire": 1}


# --- The extract command ---------------------------------------------------------------


def test_extract_gives_dataset_media_items(tmp_path, capsys):
    photo = tmp_path / "photo.jpg"
    scene(5).save(photo)
    item = extract.features(photo, classifier=FakeClassifier(), with_ocr=False)
    assert item["kind"] == "image" and len(item["phash"]) == 16
    assert set(item["extra"]["hashes"]) == {"dhash", "dhash_mirrored", "phash", "phash_mirrored"}
    assert item["extra"]["shows"][0]["label"] == "nothing"
    with pytest.raises(ValueError):
        extract.features(tmp_path / "notes.txt")
    assert extract.main([str(photo), "--no-ocr"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out[0]["file"].endswith("photo.jpg") and out[0]["kind"] == "image"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is not installed")
def test_extract_transcribes_a_voice_note(tmp_path):
    note = tmp_path / "note.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=2", str(note)], check=True)  # fmt: skip
    item = extract.features(note, recogniser=FakeASR({"note.wav": "Feni te pani barche"}))
    assert item["kind"] == "audio" and abs(item["duration_s"] - 2) < 0.2
    assert item["transcript"] == "Feni te pani barche" and "phash" not in item


def test_mirror_is_caught():
    im = scene(6)
    assert distance(hashes(im), hashes(ImageOps.mirror(im))) == 0
