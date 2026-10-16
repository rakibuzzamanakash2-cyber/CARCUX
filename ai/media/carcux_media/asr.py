"""Speech in voice notes and videos, as text (the dataset's `media[].transcript`).

Whisper through faster-whisper (`pip install -e ".[asr]"`), Bangla and English, on a
GPU when there is one. The model is downloaded on first use (about 0.5 GB for
"small", 1.5 GB for "medium"; "medium" is noticeably better on Bangla). Keep real
CARCUX recordings on your own machine: nothing here sends audio anywhere.

`FakeASR` stands in for the model in tests.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

DEFAULT_MODEL = "small"


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class Transcript:
    text: str
    language: str | None  # "bn", "en", … as the model detected or was told
    duration_s: float
    segments: list[Segment] = field(default_factory=list)


class Recogniser(Protocol):
    def transcribe(self, path: str | Path, language: str | None = None) -> Transcript: ...


class WhisperASR:
    """faster-whisper. `device="auto"` uses a GPU if CUDA is there."""

    def __init__(self, model: str = DEFAULT_MODEL, device: str = "auto", compute_type="default"):
        from faster_whisper import WhisperModel  # optional extra: .[asr]

        self.model = WhisperModel(model, device=device, compute_type=compute_type)

    def transcribe(self, path: str | Path, language: str | None = None) -> Transcript:
        segments, info = self.model.transcribe(str(path), language=language, vad_filter=True)
        segs = [Segment(s.start, s.end, s.text.strip()) for s in segments]
        return Transcript(
            text=" ".join(s.text for s in segs).strip(),
            language=info.language,
            duration_s=float(info.duration),
            segments=segs,
        )


class FakeASR:
    """Returns given transcripts by file name, for tests and dry runs."""

    def __init__(self, texts: dict[str, str] | None = None, language: str = "bn"):
        self.texts, self.language = texts or {}, language

    def transcribe(self, path: str | Path, language: str | None = None) -> Transcript:
        text = self.texts.get(Path(path).name, "")
        return Transcript(text, language or self.language, 1.0, [Segment(0.0, 1.0, text)])


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Word-level edit distance divided by the reference's length."""
    return _edits(reference.split(), hypothesis.split()) / max(len(reference.split()), 1)


def char_error_rate(reference: str, hypothesis: str) -> float:
    ref, hyp = " ".join(reference.split()), " ".join(hypothesis.split())
    return _edits(list(ref), list(hyp)) / max(len(ref), 1)


def _edits(a: list, b: list) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]
