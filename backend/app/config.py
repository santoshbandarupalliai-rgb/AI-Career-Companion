"""Application settings, loaded from environment variables / backend/.env."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Required: the app refuses to start without these.
    database_url: str
    secret_key: str = Field(min_length=32)

    # LLM (used from Phase 2 on; optional for auth-only runs).
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    # Optional fallback provider (OpenAI-compatible REST API).
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    # Providers tried in this order; ones without a key are skipped.
    llm_providers: str = "gemini,groq"

    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=30, ge=1, le=24 * 60)
    refresh_token_expire_days: int = Field(default=7, ge=1, le=90)

    frontend_origin: str = "http://localhost:5173"
    log_level: str = "INFO"
    upload_dir: Path = BACKEND_DIR / "uploads"

    @field_validator("database_url")
    @classmethod
    def _normalize_db_url(cls, v: str) -> str:
        v = v.strip()
        # Accept the plain URI Supabase shows and use the psycopg v3 driver.
        if v.startswith("postgres://"):
            v = "postgresql://" + v[len("postgres://"):]
        if v.startswith("postgresql://"):
            v = "postgresql+psycopg://" + v[len("postgresql://"):]
        if any(c in v for c in "<>[]"):
            raise ValueError("DATABASE_URL still contains template placeholders")
        return v

    @property
    def cors_origins(self) -> list[str]:
        origins = {self.frontend_origin.rstrip("/")}
        # Allow both localhost spellings for the Vite dev server.
        for o in list(origins):
            origins.add(o.replace("localhost", "127.0.0.1"))
            origins.add(o.replace("127.0.0.1", "localhost"))
        return sorted(origins)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
