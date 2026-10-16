"""Find Bangladeshi places named in text and give them coordinates.

The place finder lives in the extraction module (app/extraction/places.py, a copy of
ai/extraction): localities, upazilas, districts and divisions in English, Bangla and
Banglish spellings, with case endings, and ambiguous names settled by the districts
the text names. This module keeps the names the ingest code has always used.
"""

from app.extraction.places import (
    PRECISION_M,
    RANK,
    Place,
    best_place,
    districts,
    find_places,
    gazetteer,
)

__all__ = ["PRECISION_M", "RANK", "Place", "best_place", "districts", "find_places", "gazetteer"]
