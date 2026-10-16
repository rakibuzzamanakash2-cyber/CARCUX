"""CARCUX module 2: features from attached media, never the media itself.

- `hashing`: perceptual hashes for reused images and video frames;
- `ocr`: Bangla and English text in images (Tesseract);
- `video`: duration and frames (ffmpeg);
- `asr`: speech as text (Whisper, optional);
- `classify`: what an image shows, as CARCUX event types (CLIP, optional).
"""

from carcux_media.hashing import dhash, hamming, hashes, phash, same_image

__all__ = ["dhash", "hamming", "hashes", "phash", "same_image"]
