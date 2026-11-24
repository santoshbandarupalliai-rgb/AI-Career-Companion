import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas.profile import ResumeDetail, ResumeLabelIn, ResumeOut
from app.services import resume_service
from app.services.document_text import DocumentError

router = APIRouter(prefix="/api/resumes", tags=["Resumes"])

_NOT_FOUND = HTTPException(status_code=404, detail="Resume not found")


def _detail(resume) -> ResumeDetail:
    return ResumeDetail.model_validate(resume, from_attributes=True)


@router.post("", response_model=ResumeDetail, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload a PDF/DOCX (max 5 MB). Text is extracted and parsed; skills land as 'extracted'."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > resume_service.MAX_UPLOAD_BYTES + 64 * 1024:
        raise HTTPException(status_code=413, detail="The file is larger than 5 MB.")
    data = await file.read(resume_service.MAX_UPLOAD_BYTES + 1)
    try:
        # Parsing calls the LLM (blocking I/O), so run it off the event loop.
        resume = await run_in_threadpool(resume_service.upload, db, user.id, file.filename or "", data)
    except DocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _detail(resume)


@router.get("", response_model=list[ResumeOut])
def list_resumes(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return resume_service.list_for_user(db, user.id)


@router.get("/{resume_id}", response_model=ResumeDetail)
def get_resume(resume_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return _detail(resume_service.get_owned(db, user.id, resume_id))
    except resume_service.ResumeNotFound:
        raise _NOT_FOUND


@router.patch("/{resume_id}", response_model=ResumeOut)
def rename_resume(resume_id: uuid.UUID, payload: ResumeLabelIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Set or clear a friendly name for a resume (for example \"Backend resume\")."""
    try:
        return resume_service.rename(db, user.id, resume_id, payload.label)
    except resume_service.ResumeNotFound:
        raise _NOT_FOUND


@router.post("/{resume_id}/activate", response_model=ResumeOut)
def activate(resume_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return resume_service.set_active(db, user.id, resume_id)
    except resume_service.ResumeNotFound:
        raise _NOT_FOUND


@router.post("/{resume_id}/reextract", response_model=ResumeDetail)
def reextract(resume_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return _detail(resume_service.reextract(db, user.id, resume_id))
    except resume_service.ResumeNotFound:
        raise _NOT_FOUND


@router.get("/{resume_id}/file")
def download(resume_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        resume = resume_service.get_owned(db, user.id, resume_id)
    except resume_service.ResumeNotFound:
        raise _NOT_FOUND
    path = resume_service.file_path(resume)
    if not path.exists():
        raise HTTPException(status_code=404, detail="The stored file is missing.")
    return FileResponse(path, media_type=resume.content_type, filename=resume.original_filename)


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resume(resume_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        resume_service.delete(db, user.id, resume_id)
    except resume_service.ResumeNotFound:
        raise _NOT_FOUND
    return Response(status_code=status.HTTP_204_NO_CONTENT)
