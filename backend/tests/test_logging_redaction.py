import logging

from app.logging_config import RedactingFormatter, redact, request_id_var


def test_redacts_sql_parameters_emails_and_tokens():
    sql_error = "(psycopg.errors.UniqueViolation) duplicate key\n[SQL: INSERT INTO users (email, password_hash) VALUES (%s, %s)]\n[parameters: ('a@b.com', '$2b$12$abc')]"
    out = redact(sql_error)
    assert "a@b.com" not in out and "$2b$12" not in out and "INSERT INTO" not in out
    assert "duplicate key" in out
    assert "student@example.com" not in redact("login failed for student@example.com")
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklmnop"
    assert jwt not in redact(f"token {jwt}")
    assert "abcdefghijklmnopqrstuv" not in redact("Authorization: Bearer abcdefghijklmnopqrstuv")


def test_formatter_redacts_tracebacks_and_keeps_request_id():
    token = request_id_var.set("rid123")
    try:
        try:
            raise RuntimeError("boom for secret.person@example.com")
        except RuntimeError:
            import sys

            record = logging.LogRecord("app", logging.ERROR, __file__, 1, "unhandled error", None, sys.exc_info())
        record.request_id = "rid123"
        text = RedactingFormatter("[%(request_id)s] %(message)s").format(record)
    finally:
        request_id_var.reset(token)
    assert "[rid123]" in text and "boom for" in text
    assert "secret.person@example.com" not in text
