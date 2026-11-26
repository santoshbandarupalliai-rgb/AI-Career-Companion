"""Import every model here so Alembic autogenerate and create_all see them."""

from app.models.application import Application, ApplicationEvent
from app.models.career import GeneratedDocument, InterviewItem, InterviewSession
from app.models.chat import ChatMessage, ChatSession, MessageFeedback, PrepDocument
from app.models.internship import Internship, InternshipSkill, RagChunk, RagDocument
from app.models.profile import Resume, ResumeExtraction, Skill, StudentProfile, StudentSkill
from app.models.user import EmailToken, RefreshToken, User

__all__ = [
    "Application",
    "ApplicationEvent",
    "GeneratedDocument",
    "InterviewSession",
    "InterviewItem",
    "ChatSession",
    "ChatMessage",
    "MessageFeedback",
    "PrepDocument",
    "Internship",
    "InternshipSkill",
    "RagDocument",
    "RagChunk",
    "User",
    "RefreshToken",
    "EmailToken",
    "StudentProfile",
    "Resume",
    "ResumeExtraction",
    "Skill",
    "StudentSkill",
]
