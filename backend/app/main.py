"""FastAPI application entry point.  Run:  uvicorn app.main:app --reload --port 8000"""

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from app.config import get_settings
from app.logging_config import configure_logging, request_id_var
from app.routers import applications, auth, chat_career, chat_product, dashboard, health, internships, interview, matching, profile, resumes, skills, tailoring

settings = get_settings()
configure_logging(settings.log_level)
log = logging.getLogger("app")

app = FastAPI(
    title="AI Career Companion API",
    version="0.1.0",
    description="Career Companion backend: profiles, resume intelligence, matching, assistants.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,  # bearer tokens, no cookies
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    token = request_id_var.set(rid)
    start = time.perf_counter()
    try:
        try:
            response = await call_next(request)
        except Exception:
            log.exception("unhandled error on %s %s", request.method, request.url.path)
            response = JSONResponse(status_code=500, content={"detail": "Internal server error", "request_id": rid})
        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = rid
        log.info("%s %s -> %s (%.0f ms)", request.method, request.url.path, response.status_code, elapsed_ms)
        return response
    finally:
        request_id_var.reset(token)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    # Return readable field errors without echoing submitted values (e.g. passwords).
    errors = [
        {"field": ".".join(str(p) for p in e.get("loc", [])[1:]) or "body", "message": e.get("msg", "Invalid value")}
        for e in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": "Validation failed", "errors": errors})


@app.exception_handler(OperationalError)
async def database_unavailable_handler(request: Request, exc: OperationalError):
    # Connection-level DB failures (network drop, pooler restart) are transient: say so.
    log.error("database operational error on %s %s: %s", request.method, request.url.path, str(exc.orig)[:200])
    return JSONResponse(
        status_code=503,
        content={
            "detail": "The database is temporarily unreachable. Please try again in a moment.",
            "request_id": request_id_var.get(),
        },
    )


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(resumes.router)
app.include_router(skills.router)
app.include_router(internships.router)
app.include_router(chat_product.router)
app.include_router(matching.router)
app.include_router(matching.gap_router)
app.include_router(tailoring.router)
app.include_router(interview.router)
app.include_router(applications.router)
app.include_router(chat_career.router)
app.include_router(dashboard.router)
