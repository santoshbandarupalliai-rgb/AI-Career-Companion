import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.llm import LLMError
from app.models import GeneratedDocument, User
from app.schemas.tailoring import Draft, DocumentOut, DocumentSummary, GenerateRequest, SaveRequest
from app.services import tailoring_service
from app.services.internship_service import InternshipError
from app.services.tailoring_service import NeedsAcknowledgement, NotFound, TailoringError

router = APIRouter(prefix="/api/tailoring", tags=["Resume & Cover Letter"])

_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _out(d: GeneratedDocument) -> DocumentOut:
    return DocumentOut(id=d.id, kind=d.kind, internship_id=d.internship_id, title=d.title, content=d.content,
                       facts_used=d.facts_used or [], flagged=d.flagged or [], created_at=d.created_at)


@router.post("/generate", response_model=Draft)
async def generate(payload: GenerateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Generate a DRAFT tailored to an internship. Nothing is saved; flags list anything the fact guard could not support."""
    try:
        # The LLM call blocks, so keep it off the event loop.
        return await run_in_threadpool(tailoring_service.generate, db, user, payload.internship_id, payload.kind, payload.resume_id)
    except InternshipError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TailoringError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc) or "The AI service is unavailable right now.")


@router.post("/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def save_document(payload: SaveRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Approve and save a draft (possibly edited). The checks run again on what is submitted."""
    try:
        return _out(tailoring_service.save(db, user, payload))
    except NeedsAcknowledgement as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": str(exc), "flags": [f.model_dump() for f in exc.flags]},
        )
    except InternshipError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TailoringError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/documents", response_model=list[DocumentSummary])
def list_documents(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [
        DocumentSummary(id=d.id, kind=d.kind, title=d.title, flagged_count=len(d.flagged or []), created_at=d.created_at)
        for d in tailoring_service.list_documents(db, user.id)
    ]


@router.get("/documents/{doc_id}", response_model=DocumentOut)
def get_document(doc_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return _out(tailoring_service.get_document(db, user.id, doc_id))
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/documents/{doc_id}/download")
def download_document(doc_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        doc = tailoring_service.get_document(db, user.id, doc_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    filename = re.sub(r"[^A-Za-z0-9._-]+", "_", doc.title).strip("_")[:80] or "document"
    return Response(
        content=tailoring_service.to_docx(doc), media_type=_DOCX,
        headers={"Content-Disposition": f'attachment; filename="{filename}.docx"'},
    )


@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(doc_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        tailoring_service.delete_document(db, user.id, doc_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
