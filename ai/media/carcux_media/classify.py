"""What an image shows, as CARCUX event types: does this photo show waterlogging, a
fire, a collapsed building, a blocked road? A hint for analysts, never a decision.

Zero-shot CLIP through open_clip (`pip install -e ".[vision]"`): each label is a short
description, and the image is scored against all of them. No training data is needed,
which is why it suits a new dataset; the labels' accuracy is measured with
`python -m carcux_media.evaluate --classify FOLDER` on photos sorted into one folder
per label.

`FakeClassifier` stands in for the model in tests.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PIL import Image

# label -> (CARCUX event types it suggests, the descriptions CLIP is shown)
LABELS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "flooding": (("waterlogging", "flood", "flash_flood"),
                 ("a flooded street with people wading through water",
                  "houses and fields under flood water")),
    "fire": (("fire",), ("a building on fire with flames and smoke", "firefighters at a fire")),
    "collapse": (("building_collapse", "earthquake"),
                 ("a collapsed building with rubble", "a damaged cracked building")),
    "road_blocked": (("road_blockage",),
                     ("a road blocked by a fallen tree or debris", "a severe traffic jam")),
    "accident": (("road_accident", "rail_accident"),
                 ("a road accident with a damaged bus or car", "a derailed train")),
    "crowd": ((), ("a crowd of people protesting in the street",)),  # no event type of its own
    "landslide": (("landslide",), ("a landslide on a hillside with mud",)),
    "nothing": ((), ("an ordinary street scene", "a screenshot of text", "a portrait photo")),
}  # fmt: skip


@dataclass
class Guess:
    label: str
    score: float  # probability across the labels, 0–1
    event_types: tuple[str, ...]


class Classifier(Protocol):
    def classify(self, image: Image.Image) -> list[Guess]: ...


class ClipClassifier:
    def __init__(self, model: str = "ViT-B-32", pretrained: str = "laion2b_s34b_b79k",
                 device: str | None = None):  # fmt: skip
        import open_clip  # optional extra: .[vision]
        import torch

        self.torch = torch
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            model, pretrained=pretrained, device=self.device
        )
        tokenizer = open_clip.get_tokenizer(model)
        self.prompts = [(label, d) for label, (_, ds) in LABELS.items() for d in ds]
        with torch.no_grad():
            text = self.model.encode_text(tokenizer([d for _, d in self.prompts]).to(self.device))
            self.text = text / text.norm(dim=-1, keepdim=True)

    def classify(self, image: Image.Image) -> list[Guess]:
        torch = self.torch
        with torch.no_grad():
            x = self.preprocess(image.convert("RGB")).unsqueeze(0).to(self.device)
            v = self.model.encode_image(x)
            v = v / v.norm(dim=-1, keepdim=True)
            probs = (100.0 * v @ self.text.T).softmax(dim=-1)[0].tolist()
        by_label: dict[str, float] = {}
        for (label, _), p in zip(self.prompts, probs, strict=True):
            by_label[label] = by_label.get(label, 0.0) + p
        return _ranked(by_label)


class FakeClassifier:
    """Returns given labels by image size, for tests: {(width, height): label}."""

    def __init__(self, by_size: dict[tuple[int, int], str] | None = None):
        self.by_size = by_size or {}

    def classify(self, image: Image.Image) -> list[Guess]:
        label = self.by_size.get(image.size, "nothing")
        return _ranked({k: (0.9 if k == label else 0.1 / (len(LABELS) - 1)) for k in LABELS})


def _ranked(scores: dict[str, float]) -> list[Guess]:
    return sorted((Guess(k, round(v, 4), LABELS[k][0]) for k, v in scores.items()),
                  key=lambda g: -g.score)  # fmt: skip


def evaluate_folder(classifier: Classifier, folder: str | Path) -> dict:
    """Accuracy on photos sorted into one sub-folder per label (folder/fire/x.jpg …)."""
    total, right, confusion = 0, 0, {}
    for sub in sorted(Path(folder).iterdir()):
        if not sub.is_dir() or sub.name not in LABELS:
            continue
        for f in sorted(sub.iterdir()):
            if f.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                continue
            with Image.open(f) as im:
                top = classifier.classify(im)[0].label
            total += 1
            right += top == sub.name
            confusion.setdefault(sub.name, {}).setdefault(top, 0)
            confusion[sub.name][top] += 1
    return {"images": total, "accuracy": right / total if total else None, "confusion": confusion}
