"""Assessment suggestions: what they run on, and training a model on resolved events."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import DbSession, client_ip, require_roles
from app.models.user import Role, User
from app.schemas.assessment import AssessmentModelRead, AssessmentStatus
from app.services import assess as service

router = APIRouter(prefix="/assessment", tags=["assessment"])
Reviewer = Annotated[User, Depends(require_roles(Role.ANALYST, Role.ADMIN))]
Admin = Annotated[User, Depends(require_roles(Role.ADMIN))]


@router.get("/model", response_model=AssessmentStatus)
def model_status(db: DbSession, _user: Reviewer):
    """Starting assumptions or a trained model, its held-out results, and whether there
    are enough resolved events to train one."""
    return service.status(db)


@router.post("/model/train", response_model=AssessmentModelRead, status_code=201)
def train_model(request: Request, db: DbSession, user: Admin):
    """Learn each source's reliability and a calibration from events with ground truth,
    measure them on held-out events, and make the model active."""
    try:
        return service.train(db, user, client_ip(request))
    except service.NotEnoughDataError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None


@router.post("/model/deactivate", status_code=204)
def deactivate_model(request: Request, db: DbSession, user: Admin):
    """Go back to the starting assumptions."""
    service.deactivate(db, user, client_ip(request))
