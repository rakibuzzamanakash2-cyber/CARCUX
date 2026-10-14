"""Trained assessment models: how reliable each source has been, and how to turn the
evidence about an event into a probability that it really happened.

Each training run stores the learned reliabilities and calibration, and how well they
did on held-out events next to the starting assumptions and majority vote. At most
one model is active; without one, assessment suggestions use the starting assumptions
(services/assess.py).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AssessmentModel(Base):
    __tablename__ = "assessment_models"
    __table_args__ = (
        Index(
            "one_active_assessment_model", "active", unique=True, postgresql_where=text("active")
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    # What it learned from: events with ground truth, of which happened, and sources.
    events: Mapped[int] = mapped_column(Integer)
    happened: Mapped[int] = mapped_column(Integer)
    sources: Mapped[int] = mapped_column(Integer)
    # {"version", "rates": {source_key: rate}, "type_rates": {type: rate},
    #  "calibration": {"a", "b"} | null}
    weights: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # Held-out evaluation: {"held_out_events", "model_brier", "start_brier", ...}
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    created_by = relationship("User", lazy="joined")
