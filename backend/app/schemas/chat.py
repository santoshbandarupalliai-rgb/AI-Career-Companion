import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Citation(BaseModel):
    n: int  # the [n] marker used in the answer text
    title: str
    snippet: str
    score: float


class SessionOut(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    id: uuid.UUID
    role: Literal["user", "assistant", "tool"]
    content: str
    citations: list[Citation] = Field(default_factory=list)
    rating: int | None = None  # this user's feedback: 1, -1 or None
    created_at: datetime


class SessionDetail(BaseModel):
    session: SessionOut
    messages: list[MessageOut]


class SessionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=120)


class SendMessage(BaseModel):
    content: str = Field(min_length=1, max_length=2000)

    @field_validator("content")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Message cannot be empty")
        return v


class SendResponse(BaseModel):
    session: SessionOut
    user_message: MessageOut
    assistant_message: MessageOut


class FeedbackIn(BaseModel):
    rating: Literal[1, -1]


# ---------- Career Assistant ----------

class ToolStepOut(BaseModel):
    tool: str
    args: dict = Field(default_factory=dict)
    ok: bool
    summary: str


class ActionOut(BaseModel):
    id: str
    kind: Literal["track", "status"]
    label: str
    state: Literal["pending", "done", "cancelled", "failed"]
    result: str | None = None


class CareerMessageOut(BaseModel):
    id: uuid.UUID
    role: Literal["user", "assistant", "tool"]
    content: str
    steps: list[ToolStepOut] = Field(default_factory=list)
    actions: list[ActionOut] = Field(default_factory=list)
    rating: int | None = None
    created_at: datetime


class CareerSessionDetail(BaseModel):
    session: SessionOut
    messages: list[CareerMessageOut]


class CareerSendResponse(BaseModel):
    session: SessionOut
    user_message: CareerMessageOut
    assistant_message: CareerMessageOut


class ActionDecision(BaseModel):
    decision: Literal["confirm", "cancel"]


class PrepDocumentOut(BaseModel):
    id: uuid.UUID
    filename: str
    char_count: int
    created_at: datetime


class PrepSessionDetail(SessionDetail):
    documents: list[PrepDocumentOut] = Field(default_factory=list)
