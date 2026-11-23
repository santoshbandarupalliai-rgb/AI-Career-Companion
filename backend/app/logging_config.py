"""Logging setup with a per-request correlation id."""

import logging
import re
import sys
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_base_factory = logging.getLogRecordFactory()


def _record_factory(*args, **kwargs) -> logging.LogRecord:
    # Every log record (from any logger or handler) carries the current request id.
    record = _base_factory(*args, **kwargs)
    record.request_id = request_id_var.get()
    return record


# Exception text from the database driver can embed the SQL statement and its bound parameters
# (emails, password hashes, resume text). Tokens and addresses must never reach the log either.
_REDACTIONS = [
    (re.compile(r"\[SQL:.*?\]\s*\[parameters:.*?\]", re.S), "[SQL and parameters omitted]"),
    (re.compile(r"\[parameters:.*?\]", re.S), "[parameters omitted]"),
    (re.compile(r"eyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}"), "[token]"),
    (re.compile(r"(?i)bearer\s+[\w.~+/=-]{12,}"), "Bearer [token]"),
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[email]"),
]


def redact(text: str) -> str:
    for pattern, repl in _REDACTIONS:
        text = pattern.sub(repl, text)
    return text


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def configure_logging(level: str = "INFO") -> None:
    logging.setLogRecordFactory(_record_factory)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        RedactingFormatter("%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    # Keep noisy libraries quiet unless debugging.
    for name in ("sqlalchemy.engine", "httpx", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)
