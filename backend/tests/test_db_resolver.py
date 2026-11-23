from app.db import CachedResolver


def test_resolver_caches_and_falls_back_when_dns_fails(monkeypatch):
    r = CachedResolver("db.example.test", 5432, ttl=0)  # ttl=0: refresh on every call
    answers = iter([["10.0.0.1", "10.0.0.2"], [], []])
    monkeypatch.setattr(r, "_lookup", lambda: next(answers))
    assert r.ip() in {"10.0.0.1", "10.0.0.2"}
    # DNS now fails: the last good answer is still used.
    assert r.ip() in {"10.0.0.1", "10.0.0.2"}
    assert r.ip() in {"10.0.0.1", "10.0.0.2"}


def test_resolver_retries_first_lookup(monkeypatch):
    r = CachedResolver("db.example.test", 5432)
    answers = iter([[], [], ["10.0.0.9"]])
    monkeypatch.setattr(r, "_lookup", lambda: next(answers))
    assert r.ip() == "10.0.0.9"


def test_resolver_returns_none_when_never_resolved(monkeypatch):
    r = CachedResolver("db.example.test", 5432)
    monkeypatch.setattr(r, "_lookup", lambda: [])
    assert r.ip() is None  # libpq then falls back to normal resolution
