"""Trained models that rank events as suggestions for a report or a signal.

Each training run stores its weights and how well it did on held-out events, next to
the 5 km / 48 h rule on the same items. At most one model is active; without an active
model the suggestions fall back to the rule (services/suggest.py).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SuggestionModel(Base):
    __tablename__ = "suggestion_models"
    __table_args__ = (
        # At most one active model.
        Index(
            "one_active_suggestion_model", "active", unique=True, postgresql_where=text("active")
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    # What it learned from: labelled items, distinct events, training rows.
    items: Mapped[int] = mapped_column(Integer)
    events: Mapped[int] = mapped_column(Integer)
    positives: Mapped[int] = mapped_column(Integer)
    negatives: Mapped[int] = mapped_column(Integer)
    # {"names": [...], "mean": [...], "scale": [...], "coef": [...], "intercept": float}
    weights: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # Held-out evaluation: {"held_out_items", "model_top1", "rule_top1", "model_top3", ...}
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    created_by = relationship("User", lazy="joined")
