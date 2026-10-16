"""Official pages. Admins create, verify, suspend and staff them; everyone signed in can
read verified pages; an official sees their own page whatever its state."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.deps import AppSettings, CurrentUser, DbSession, client_ip, require_roles
from app.models.official import OfficialPage, PageStatus
from app.models.user import Role, User
from app.schemas.official import (
    Member,
    MemberCreate,
    OfficialPageCreate,
    OfficialPageDetail,
    OfficialPageRead,
    OfficialPageUpdate,
    Suspension,
    Verification,
)
from app.schemas.user import UserRead
from app.services import official as service
from app.services.media import resolve
from app.services.users import EmailAlreadyRegisteredError, create_user

router = APIRouter(prefix="/official-pages", tags=["official pages"])

AdminUser = Annotated[User, Depends(require_roles(Role.ADMIN))]


def _rule(exc: Exception) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))


def _detail(page: OfficialPage) -> OfficialPageDetail:
    return OfficialPageDetail.model_validate(
        {
            **{k: getattr(page, k) for k in OfficialPageDetail.model_fields if hasattr(page, k)},
            "website": page.website,
            "has_document": page.document_key is not None,
            "members": [Member.model_validate(m) for m in page.members if m.role == Role.OFFICIAL],
        }
    )


def _page_or_404(db, page_id: uuid.UUID) -> OfficialPage:
    page = db.get(OfficialPage, page_id)
    if page is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Official page not found")
    return page


def _can_see_detail(page: OfficialPage, user: User) -> bool:
    return user.role == Role.ADMIN or user.official_page_id == page.id


@router.get("", response_model=list[OfficialPageRead])
def list_pages(db: DbSession, user: CurrentUser):
    """Admins see every page; everyone else the verified ones."""
    query = select(OfficialPage).order_by(OfficialPage.name)
    if user.role != Role.ADMIN:
        query = query.where(OfficialPage.status == PageStatus.VERIFIED)
    return db.scalars(query).all()


@router.get("/mine", response_model=OfficialPageDetail)
def my_page(db: DbSession, user: CurrentUser):
    if user.official_page_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "You do not speak for an official page")
    return _detail(_page_or_404(db, user.official_page_id))


@router.get("/by-slug/{slug}", response_model=OfficialPageDetail | OfficialPageRead)
def by_slug(slug: str, db: DbSession, user: CurrentUser):
    page = service.by_slug(db, slug)
    if page is None or not service.visible_to(page, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Official page not found")
    return _detail(page) if _can_see_detail(page, user) else OfficialPageRead.model_validate(page)


@router.post("", response_model=OfficialPageDetail, status_code=status.HTTP_201_CREATED)
def create(body: OfficialPageCreate, request: Request, db: DbSession, admin: AdminUser):
    data = body.model_dump()
    data["website"] = str(body.website) if body.website else None
    try:
        page = service.create(db, actor=admin, ip=client_ip(request), **data)
    except ValueError as exc:
        raise _rule(exc) from None
    db.commit()
    return _detail(page)


@router.patch("/{page_id}", response_model=OfficialPageDetail)
def update(
    page_id: uuid.UUID, body: OfficialPageUpdate, request: Request, db: DbSession, admin: AdminUser
):
    page = _page_or_404(db, page_id)
    changes = body.model_dump(exclude_unset=True)
    if "website" in changes and changes["website"] is not None:
        changes["website"] = str(changes["website"])
    for required in ("name", "kind"):
        if required in changes and changes[required] is None:
            raise _rule(ValueError(f"{required} cannot be empty"))
    try:
        service.update(db, page, changes, actor=admin, ip=client_ip(request))
    except ValueError as exc:
        raise _rule(exc) from None
    db.commit()
    return _detail(page)


@router.post("/{page_id}/document", response_model=OfficialPageDetail)
async def add_document(
    page_id: uuid.UUID,
    request: Request,
    db: DbSession,
    settings: AppSettings,
    admin: AdminUser,
    file: Annotated[UploadFile, File(description="The official letter: PDF, JPEG or PNG")],
):
    page = _page_or_404(db, page_id)
    data = await file.read(service.MAX_DOCUMENT_BYTES + 1)
    try:
        service.add_document(db, page, data, settings.media_dir, actor=admin, ip=client_ip(request))
    except ValueError as exc:
        raise _rule(exc) from None
    db.commit()
    return _detail(page)


@router.get("/{page_id}/document")
def get_document(page_id: uuid.UUID, db: DbSession, settings: AppSettings, _admin: AdminUser):
    page = _page_or_404(db, page_id)
    if not page.document_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No letter on file")
    path = resolve(settings.media_dir, page.document_key)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The letter's file is missing")
    return FileResponse(
        path,
        media_type=page.document_type,
        filename=f"{page.slug}-verification{path.suffix}",
        headers={"Cache-Control": "private, no-store"},
    )


@router.post("/{page_id}/verify", response_model=OfficialPageDetail)
def verify(
    page_id: uuid.UUID, body: Verification, request: Request, db: DbSession, admin: AdminUser
):
    page = _page_or_404(db, page_id)
    try:
        service.verify(db, page, body.method, body.note, actor=admin, ip=client_ip(request))
    except ValueError as exc:
        raise _rule(exc) from None
    db.commit()
    return _detail(page)


@router.post("/{page_id}/suspend", response_model=OfficialPageDetail)
def suspend(
    page_id: uuid.UUID, body: Suspension, request: Request, db: DbSession, admin: AdminUser
):
    page = _page_or_404(db, page_id)
    try:
        service.suspend(db, page, body.reason, actor=admin, ip=client_ip(request))
    except ValueError as exc:
        raise _rule(exc) from None
    db.commit()
    return _detail(page)


@router.post("/{page_id}/reinstate", response_model=OfficialPageDetail)
def reinstate(page_id: uuid.UUID, request: Request, db: DbSession, admin: AdminUser):
    page = _page_or_404(db, page_id)
    try:
        service.reinstate(db, page, actor=admin, ip=client_ip(request))
    except ValueError as exc:
        raise _rule(exc) from None
    db.commit()
    return _detail(page)


@router.post("/{page_id}/members", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def add_member(
    page_id: uuid.UUID, body: MemberCreate, request: Request, db: DbSession, admin: AdminUser
):
    """An official account for this page (a named person at the office)."""
    page = _page_or_404(db, page_id)
    try:
        spec = body.as_user(page.id)
        user = create_user(
            db, email=spec.email, full_name=spec.full_name, password=spec.password,
            role=Role.OFFICIAL, official_page_id=page.id, actor_id=admin.id,
            ip_address=client_ip(request),
        )  # fmt: skip
    except EmailAlreadyRegisteredError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from None
    except ValueError as exc:
        raise _rule(exc) from None
    db.commit()
    return user
