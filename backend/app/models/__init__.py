"""Import every model here so Alembic autogenerate and create_all see them."""

from app.models.internship import Internship, InternshipSkill, RagChunk, RagDocument
from app.models.profile import Resume, ResumeExtraction, Skill, StudentProfile, StudentSkill
from app.models.user import RefreshToken, User

__all__ = [
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
