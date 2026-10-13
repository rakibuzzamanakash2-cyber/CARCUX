"""Event suggestions: what they run on, and training a model from analysts' links."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import DbSession, client_ip, require_roles
from app.models.user import Role, User
from app.schemas.event import CandidateEvent, EventRead, SuggestionModelRead, SuggestionStatus
from app.services import suggest as service

router = APIRouter(prefix="/suggestions", tags=["suggestions"])
Reviewer = Annotated[User, Depends(require_roles(Role.ANALYST, Role.ADMIN))]
Admin = Annotated[User, Depends(require_roles(Role.ADMIN))]


def as_candidate(s: service.Suggestion) -> CandidateEvent:
    return CandidateEvent(
        event=EventRead.model_validate(s.event),
        distance_km=s.distance_km,
        hours_apart=s.hours_apart,
        same_type=s.same_type,
        same_family=s.same_family,
        method=s.method,
        score=s.score,
        text_similarity=s.text_similarity,
        hours_from_latest=s.hours_from_latest,
        model_id=s.model_id,
    )


@router.get("/model", response_model=SuggestionStatus)
def model_status(db: DbSession, _user: Reviewer):
    """Rule or model, the active model's held-out results, and whether there are enough
    links to train one."""
    return service.status(db)


@router.post("/model/train", response_model=SuggestionModelRead, status_code=201)
def train_model(request: Request, db: DbSession, user: Admin):
    """Train a model on every link analysts have made (gold labels where adjudicated),
    measure it against the rule on held-out events, and make it the active model."""
    try:
        return service.train(db, user, client_ip(request))
    except service.NotEnoughDataError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None


@router.post("/model/deactivate", status_code=204)
def deactivate_model(request: Request, db: DbSession, user: Admin):
    """Go back to the 5 km / 48 h rule."""
    service.deactivate(db, user, client_ip(request))
