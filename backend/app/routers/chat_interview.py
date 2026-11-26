"""Interview Prep Agent API: chat sessions, messages and documents for document-based Q&A."""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.llm import LLMError
from app.models import ChatMessage, ChatSession, PrepDocument, User
from app.rag.embeddings import EmbeddingError
from app.schemas.chat import (
    FeedbackIn,
    MessageOut,
    PrepDocumentOut,
    PrepSessionDetail,
    SendMessage,
    SendResponse,
    SessionCreate,
    SessionOut,
)
from app.services import chat_repo, interview_agent
from app.services.chat_repo import ChatNotFound
from app.services.interview_agent import PrepError

router = APIRouter(prefix="/api/chat/interview", tags=["Interview Prep Agent"])
T = interview_agent.ASSISTANT_TYPE


def _session_out(s: ChatSession) -> SessionOut:
    return SessionOut(id=s.id, title=s.title, created_at=s.created_at, updated_at=s.updated_at)


def _msg_out(m: ChatMessage, rating: int | None = None) -> MessageOut:
    return MessageOut(id=m.id, role=m.role, content=m.content, citations=m.citations or [], rating=rating, created_at=m.created_at)


def _doc_out(d: PrepDocument) -> PrepDocumentOut:
    return PrepDocumentOut(id=d.id, filename=d.filename, char_count=d.char_count, created_at=d.created_at)


def _404(exc: ChatNotFound) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [_session_out(s) for s in chat_repo.list_sessions(db, user.id, T)]


@router.post("/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def create_session(payload: SessionCreate | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    title = (payload.title.strip() if payload and payload.title else "") or "New chat"
    return _session_out(chat_repo.create_session(db, user.id, T, title))


@router.get("/sessions/{session_id}", response_model=PrepSessionDetail)
def get_session(session_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        session = chat_repo.get_session(db, user.id, T, session_id)
        messages = chat_repo.get_messages(db, user.id, T, session_id)
        docs = interview_agent.list_documents(db, user.id, session_id)
    except ChatNotFound as exc:
        raise _404(exc)
    ratings = chat_repo.feedback_for(db, user.id, [m.id for m in messages])
    return PrepSessionDetail(session=_session_out(session), messages=[_msg_out(m, ratings.get(m.id)) for m in messages],
                             documents=[_doc_out(d) for d in docs])


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        interview_agent.delete_session(db, user.id, session_id)
    except ChatNotFound as exc:
        raise _404(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sessions/{session_id}/messages", response_model=SendResponse)
async def send_message(session_id: uuid.UUID, payload: SendMessage, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        user_msg, asst_msg = await run_in_threadpool(interview_agent.run, db, user.id, session_id, payload.content)
        session = chat_repo.get_session(db, user.id, T, session_id)
    except ChatNotFound as exc:
        raise _404(exc)
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc) or "The AI service is unavailable right now. Please try again in a moment.")
    except EmbeddingError:
        raise HTTPException(status_code=503, detail="The search model is unavailable right now. Please try again shortly.")
    return SendResponse(session=_session_out(session), user_message=_msg_out(user_msg), assistant_message=_msg_out(asst_msg))


@router.put("/messages/{message_id}/feedback", response_model=MessageOut)
def rate_message(message_id: uuid.UUID, payload: FeedbackIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        msg = chat_repo.set_feedback(db, user.id, T, message_id, payload.rating)
    except ChatNotFound as exc:
        raise _404(exc)
    return _msg_out(msg, payload.rating)


@router.post("/sessions/{session_id}/documents", response_model=PrepDocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    session_id: uuid.UUID, request: Request, file: UploadFile = File(...),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Attach a PDF or DOCX (max 5 MB) to the chat. Its text is extracted and indexed for questions."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > interview_agent.MAX_DOC_BYTES + 64 * 1024:
        raise HTTPException(status_code=413, detail="The file is larger than 5 MB.")
    data = await file.read(interview_agent.MAX_DOC_BYTES + 1)
    try:
        doc = await run_in_threadpool(interview_agent.upload_document, db, user.id, session_id, file.filename or "", data)
    except ChatNotFound as exc:
        raise _404(exc)
    except PrepError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EmbeddingError:
        raise HTTPException(status_code=503, detail="The search model is unavailable right now. Please try again shortly.")
    return _doc_out(doc)


@router.get("/sessions/{session_id}/documents", response_model=list[PrepDocumentOut])
def list_documents(session_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return [_doc_out(d) for d in interview_agent.list_documents(db, user.id, session_id)]
    except ChatNotFound as exc:
        raise _404(exc)


@router.delete("/sessions/{session_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(session_id: uuid.UUID, document_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        interview_agent.delete_document(db, user.id, session_id, document_id)
    except ChatNotFound as exc:
        raise _404(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
