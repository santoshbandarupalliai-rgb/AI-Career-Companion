"""Confirm or cancel an action the Career Assistant proposed. This is the ONLY path by which
the assistant's suggestions change data, and it runs on an explicit click by the student.

The action parameters are read from the stored message (server-side), never from the client,
and each action can be resolved once.
"""

import uuid
from typing import Literal

from sqlalchemy.orm import Session

from app.models import ChatMessage
from app.schemas.application import ApplicationCreate
from app.services import application_service, chat_repo
from app.services.application_service import STATUS_LABELS

ASSISTANT_TYPE = "career"


class ActionNotFound(LookupError):
    pass


class ActionAlreadyResolved(ValueError):
    pass


def _find(msg: ChatMessage, action_id: str) -> tuple[list[dict], dict]:
    calls = [dict(t) for t in (msg.tool_calls or [])]
    for t in calls:
        if t.get("type") == "action" and t.get("id") == action_id:
            return calls, t
    raise ActionNotFound("Action not found")


def _execute(db: Session, user_id: uuid.UUID, action: dict) -> str:
    p = action["params"]
    if action["kind"] == "track":
        app = application_service.create(
            db, user_id, ApplicationCreate(internship_id=uuid.UUID(p["internship_id"]), status=p["status"])
        )
        return f"Added to your tracker as {STATUS_LABELS[app.status]}."
    if action["kind"] == "status":
        app = application_service.get(db, user_id, uuid.UUID(p["application_id"]))
        before = app.status
        application_service.change_status(db, user_id, app.id, p["status"], p.get("note"))
        return f"Status changed from {STATUS_LABELS[before]} to {STATUS_LABELS[p['status']]}."
    raise ActionNotFound("Unknown action")


def resolve(
    db: Session, user_id: uuid.UUID, message_id: uuid.UUID, action_id: str, decision: Literal["confirm", "cancel"]
) -> ChatMessage:
    msg = chat_repo.get_assistant_message(db, user_id, ASSISTANT_TYPE, message_id, for_update=True)
    _, action = _find(msg, action_id)
    if action.get("state") != "pending":
        raise ActionAlreadyResolved(f"This action was already {action.get('state')}.")

    if decision == "cancel":
        state, result = "cancelled", "Cancelled. Nothing was changed."
    else:
        try:
            state, result = "done", _execute(db, user_id, action)
        except (application_service.ApplicationError, application_service.ApplicationNotFound) as exc:
            db.rollback()
            state, result = "failed", str(exc)

    # Re-read: _execute committed (which released the row lock and may have expired the object).
    msg = chat_repo.get_assistant_message(db, user_id, ASSISTANT_TYPE, message_id, for_update=True)
    calls, action = _find(msg, action_id)
    if action.get("state") != "pending":  # resolved concurrently by another request
        db.rollback()
        raise ActionAlreadyResolved(f"This action was already {action.get('state')}.")
    action.update(state=state, result=result)
    chat_repo.set_tool_calls(msg, calls)
    db.commit()
    return msg
