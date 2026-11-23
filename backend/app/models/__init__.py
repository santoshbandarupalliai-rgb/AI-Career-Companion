"""Import every model here so Alembic autogenerate and create_all see them."""

from app.models.application import Application, ApplicationEvent
from app.models.career import GeneratedDocument, InterviewItem, InterviewSession
from app.models.chat import ChatMessage, ChatSession, MessageFeedback
from app.models.internship import Internship, InternshipSkill, RagChunk, RagDocument
from app.models.profile import Resume, ResumeExtraction, Skill, StudentProfile, StudentSkill
from app.models.user import RefreshToken, User

__all__ = [
    "Application",
    "ApplicationEvent",
    "GeneratedDocument",
    "InterviewSession",
    "InterviewItem",
    "ChatSession",
    "ChatMessage",
    "MessageFeedback",
    "Internship",
    "InternshipSkill",
    "RagDocument",
    "RagChunk",
    "User",
    "RefreshToken",
    "StudentProfile",
    "Resume",
    "ResumeExtraction",
    "Skill",
    "StudentSkill",
]
