import logging

from fastapi import APIRouter

from app.main import app

_boom = APIRouter()


@_boom.get("/api/_test/boom")
def boom():
    raise RuntimeError("simulated failure")


app.include_router(_boom)


def test_unhandled_error_returns_clean_500_with_request_id(client, caplog):
    with caplog.at_level(logging.INFO):
        r = client.get("/api/_test/boom", headers={"X-Request-ID": "abc123"})
    assert r.status_code == 500
    assert r.json() == {"detail": "Internal server error", "request_id": "abc123"}
    assert "simulated failure" not in r.text  # no stack traces leak to clients
    # Log lines for this request carry its id.
    assert any(getattr(rec, "request_id", None) == "abc123" for rec in caplog.records if rec.name == "app")
