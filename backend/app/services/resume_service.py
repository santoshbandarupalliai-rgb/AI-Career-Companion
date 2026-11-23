"""Resume upload, storage, extraction and lifecycle."""

import logging
import time
import uuid
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Resume, ResumeExtraction
from app.services import resume_parser, skill_service
from app.services.document_text import DocumentError, extract_text

log = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_RESUMES_PER_USER = 10
CONTENT_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class ResumeNotFound(LookupError):
    pass


def _user_dir(user_id: uuid.UUID) -> Path:
    d = get_settings().upload_dir / str(user_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def file_path(resume: Resume) -> Path:
    return _user_dir(resume.user_id) / resume.stored_filename


def get_owned(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID) -> Resume:
    resume = db.scalar(select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id))
    if resume is None:
        raise ResumeNotFound
    return resume


def list_for_user(db: Session, user_id: uuid.UUID) -> list[Resume]:
    return list(db.scalars(select(Resume).where(Resume.user_id == user_id).order_by(Resume.uploaded_at.desc())))


def active_resume(db: Session, user_id: uuid.UUID) -> Resume | None:
    return db.scalar(select(Resume).where(Resume.user_id == user_id, Resume.is_active.is_(True)))


PERSIST_ATTEMPTS = 3


def _save_extraction(db: Session, resume_id: uuid.UUID, result: resume_parser.ParseResult) -> None:
    """Store the parse result and skills in one transaction, retrying on dropped connections.

    The (slow, paid) LLM call has already happened; a retry only repeats the database work.
    """
    payload = dict(
        data=result.data.model_dump(), method=result.method, model=result.model, warnings=result.warnings
    )
    for attempt in range(1, PERSIST_ATTEMPTS + 1):
        try:
            resume = db.get(Resume, resume_id)
            if resume is None:  # deleted while parsing
                return
            if resume.extraction is None:
                resume.extraction = ResumeExtraction(**payload)
            else:
                for k, v in payload.items():
                    setattr(resume.extraction, k, v)
            resume.extraction_status = result.status
            skill_service.sync_from_resume(
                db, resume.user_id, resume.id, resume_parser.all_skills(result.data), resume.raw_text
            )
            db.commit()
            return
        except (OperationalError, IntegrityError) as exc:
            db.rollback()
            log.warning("saving extraction failed (attempt %d/%d): %s", attempt, PERSIST_ATTEMPTS, type(exc).__name__)
            if attempt == PERSIST_ATTEMPTS:
                raise
            time.sleep(attempt)


def _run_extraction(db: Session, resume: Resume) -> None:
    """Parse the resume text and store the result. Commits."""
    try:
        result = resume_parser.parse_resume(resume.raw_text)
    except Exception:
        log.exception("resume extraction crashed resume=%s", resume.id)
        resume.extraction_status = "failed"
        db.commit()
        return
    _save_extraction(db, resume.id, result)
    log.info("resume extracted resume=%s method=%s status=%s", resume.id, result.method, result.status)


def upload(db: Session, user_id: uuid.UUID, filename: str, data: bytes) -> Resume:
    if not data:
        raise DocumentError("The file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise DocumentError("The file is larger than 5 MB.")
    count = len(list_for_user(db, user_id))
    if count >= MAX_RESUMES_PER_USER:
        raise DocumentError(f"You can keep up to {MAX_RESUMES_PER_USER} resumes. Delete an old one first.")

    safe_name = Path(filename or "resume").name[:200]
    kind, extracted = extract_text(safe_name, data)

    stored = f"{uuid.uuid4().hex}.{kind}"
    path = _user_dir(user_id) / stored
    path.write_bytes(data)
    try:
        # The newest upload becomes the active resume.
        db.execute(update(Resume).where(Resume.user_id == user_id).values(is_active=False))
        resume = Resume(
            user_id=user_id,
            original_filename=safe_name,
            stored_filename=stored,
            content_type=CONTENT_TYPES[kind],
            size_bytes=len(data),
            page_count=extracted.page_count,
            raw_text=extracted.text,
            is_active=True,
            extraction_status="pending",
        )
        db.add(resume)
        db.commit()
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    _run_extraction(db, resume)
    db.refresh(resume)
    return resume


def reextract(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID) -> Resume:
    resume = get_owned(db, user_id, resume_id)
    _run_extraction(db, resume)
    db.refresh(resume)
    return resume


def set_active(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID) -> Resume:
    resume = get_owned(db, user_id, resume_id)
    db.execute(update(Resume).where(Resume.user_id == user_id).values(is_active=False))
    resume.is_active = True
    db.commit()
    db.refresh(resume)
    return resume


def delete(db: Session, user_id: uuid.UUID, resume_id: uuid.UUID) -> None:
    resume = get_owned(db, user_id, resume_id)
    was_active = resume.is_active
    path = file_path(resume)
    skill_service.remove_unverified_from_resume(db, user_id, resume.id)
    db.delete(resume)
    db.flush()
    if was_active:
        newest = db.scalar(
            select(Resume).where(Resume.user_id == user_id).order_by(Resume.uploaded_at.desc()).limit(1)
        )
        if newest:
            newest.is_active = True
    db.commit()
    path.unlink(missing_ok=True)
