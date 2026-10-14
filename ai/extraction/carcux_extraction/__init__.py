"""CARCUX module 1: structured details from Bangla, Banglish and English text."""

from carcux_extraction.claims import Claim, extract
from carcux_extraction.language import detect_language

__all__ = ["Claim", "detect_language", "extract"]
