"""Video and audio: duration, and frames to hash, with the ffmpeg programs.

A frame every few seconds is enough to spot a reposted clip: reposts are usually
trimmed, re-encoded or captioned, but most of their frames survive. Frames are hashed
like images (`hashing.hashes`).
"""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from carcux_media.hashing import hashes, same_image

FRAME_EVERY_S = 2.0
MAX_FRAMES = 60


class FFmpegUnavailableError(RuntimeError):
    pass


def available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def probe(path: str | Path) -> dict:
    """Duration in seconds, and whether there is video and audio."""
    if not available():
        raise FFmpegUnavailableError("ffmpeg and ffprobe are not installed")
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        capture_output=True, check=True, timeout=60,
    ).stdout  # fmt: skip
    info = json.loads(out)
    kinds = {s.get("codec_type") for s in info.get("streams", [])}
    duration = float(info.get("format", {}).get("duration") or 0.0)
    return {"duration_s": duration, "video": "video" in kinds, "audio": "audio" in kinds}


def frames(path: str | Path, every_s: float = FRAME_EVERY_S, limit: int = MAX_FRAMES):
    """Frames sampled every `every_s` seconds (at most `limit`), as images."""
    if not available():
        raise FFmpegUnavailableError("ffmpeg and ffprobe are not installed")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"fps=1/{every_s},scale=320:-2",
             "-frames:v", str(limit), f"{tmp}/f%04d.png"],
            capture_output=True, check=True, timeout=300,
        )  # fmt: skip
        out = []
        for f in sorted(Path(tmp).glob("f*.png")):
            with Image.open(f) as im:
                out.append(im.copy())
        return out


def frame_hashes(path: str | Path, every_s: float = FRAME_EVERY_S) -> list[dict[str, str]]:
    return [hashes(f) for f in frames(path, every_s)]


def shared_frames(a: list[dict[str, str]], b: list[dict[str, str]]) -> float:
    """The share of the shorter clip's frames that appear in the other clip."""
    if not a or not b:
        return 0.0
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return sum(any(same_image(x, y) for y in long_) for x in short) / len(short)
