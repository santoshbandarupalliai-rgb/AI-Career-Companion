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
