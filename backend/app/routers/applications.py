"""Application tracker API (module 8)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Application, User
from app.schemas.application import (
    ApplicationCreate,
    ApplicationDetail,
    ApplicationList,
    ApplicationOut,
    ApplicationUpdate,
    ApplyRequest,
    EventOut,
    Status,
    StatusChange,
)
from app.services import application_service as svc

router = APIRouter(prefix="/api/applications", tags=["Applications"])


def _out(a: Application, meta: tuple[str | None, str | None]) -> dict:
    return dict(
        id=a.id, internship_id=a.internship_id, internship_source=meta[0], company=a.company, role=a.role,
        status=a.status, applied_on=a.applied_on, deadline=a.deadline, resume_id=a.resume_id, resume_name=meta[1], stipend=meta[2],
        notes=a.notes, created_at=a.created_at, updated_at=a.updated_at,
    )


def _detail(db: Session, a: Application) -> ApplicationDetail:
    meta = svc.describe(db, [a])[a.id]
    events = [EventOut(id=e.id, from_status=e.from_status, to_status=e.to_status, note=e.note, created_at=e.created_at)
              for e in a.events]
    return ApplicationDetail(**_out(a, meta), events=events)


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, svc.ApplicationNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, svc.ApplicationConflict):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


_ERRORS = (svc.ApplicationNotFound, svc.ApplicationError)


@router.get("", response_model=ApplicationList)
def list_applications(
    status_: Status | None = Query(default=None, alias="status"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items, counts = svc.list_applications(db, user.id, status_)
    meta = svc.describe(db, items)
    return ApplicationList(items=[ApplicationOut(**_out(a, meta[a.id])) for a in items], counts=counts)


@router.post("", response_model=ApplicationDetail, status_code=status.HTTP_201_CREATED)
def create_application(payload: ApplicationCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        a = svc.create(db, user.id, payload)
    except _ERRORS as exc:
        raise _http(exc)
    return _detail(db, a)


@router.post("/apply", response_model=ApplicationDetail, status_code=status.HTTP_201_CREATED)
def apply(payload: ApplyRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Demo apply: mark an internship as Applied in the tracker. Nothing is sent to the company."""
    try:
        a = svc.apply(db, user.id, payload.internship_id, payload.resume_id, payload.notes)
    except _ERRORS as exc:
        raise _http(exc)
    return _detail(db, a)


@router.get("/{application_id}", response_model=ApplicationDetail)
def get_application(application_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return _detail(db, svc.get(db, user.id, application_id))
    except _ERRORS as exc:
        raise _http(exc)


@router.patch("/{application_id}", response_model=ApplicationDetail)
def update_application(
    application_id: uuid.UUID, payload: ApplicationUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    try:
        return _detail(db, svc.update(db, user.id, application_id, payload))
    except _ERRORS as exc:
        raise _http(exc)


@router.post("/{application_id}/status", response_model=ApplicationDetail)
def change_status(
    application_id: uuid.UUID, payload: StatusChange, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    try:
        return _detail(db, svc.change_status(db, user.id, application_id, payload.status, payload.note))
    except _ERRORS as exc:
        raise _http(exc)


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_application(application_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        svc.delete(db, user.id, application_id)
    except _ERRORS as exc:
        raise _http(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
