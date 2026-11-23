"""Logging setup with a per-request correlation id."""

import logging
import sys
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_base_factory = logging.getLogRecordFactory()


def _record_factory(*args, **kwargs) -> logging.LogRecord:
    # Every log record (from any logger or handler) carries the current request id.
    record = _base_factory(*args, **kwargs)
    record.request_id = request_id_var.get()
    return record


def configure_logging(level: str = "INFO") -> None:
    logging.setLogRecordFactory(_record_factory)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    # Keep noisy libraries quiet unless debugging.
    for name in ("sqlalchemy.engine", "httpx", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)
