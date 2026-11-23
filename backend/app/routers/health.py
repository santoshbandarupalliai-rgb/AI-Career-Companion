import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db

router = APIRouter(prefix="/api", tags=["Health"])
log = logging.getLogger(__name__)


@router.get("/health")
def health(db: Session = Depends(get_db)):
    """Liveness plus a database round-trip."""
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
    except Exception:
        log.exception("health check: database unreachable")
        return JSONResponse(status_code=503, content={"status": "degraded", "database": "unreachable"})
