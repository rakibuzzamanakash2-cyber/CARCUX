"""CARCUX module 6, decision support: helping people decide without deciding for them.

- `priority.suggest`: a suggested priority from operational factors only, each with
  its reason;
- `summary.summarise`: a summary in which every sentence cites the items it rests on;
- `changes.what_changed`: what is new since a moment.

Standard library only, so the backend can use it as it is (app/decision_support).
"""

from app.decision_support.changes import LogEntry, what_changed
from app.decision_support.model import Detail, Estimate, EventFacts, Evidence
from app.decision_support.priority import Factor, PrioritySuggestion, suggest
from app.decision_support.summary import Sentence, summarise

__all__ = [
    "Detail",
    "Estimate",
    "EventFacts",
    "Evidence",
    "Factor",
    "LogEntry",
    "PrioritySuggestion",
    "Sentence",
    "suggest",
    "summarise",
    "what_changed",
]
