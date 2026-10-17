"""Details from Bangla, Banglish and English text: a copy of the extraction module
(ai/extraction/carcux_extraction), so the backend image needs nothing outside backend/.

Do not edit these files here. Change ai/extraction, then copy it over:

    python backend/scripts/sync_extraction.py

tests/test_extraction_copy.py fails when the copy and the original differ.
"""

from app.extraction.claims import Claim, extract
from app.extraction.language import detect_language
from app.extraction.places import Place, best_place, find_places
from app.extraction.times import TimeMention, observed_at, times

VERSION = "rules-0.2"

__all__ = [
    "VERSION",
    "Claim",
    "Place",
    "TimeMention",
    "best_place",
    "detect_language",
    "extract",
    "find_places",
    "observed_at",
    "times",
]
