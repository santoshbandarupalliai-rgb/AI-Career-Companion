"""Database engine, session factory and declarative base."""

import logging
import random
import socket
import threading
import time
from collections.abc import Generator

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

log = logging.getLogger(__name__)

# Deterministic constraint names so Alembic migrations stay stable.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class CachedResolver:
    """Resolves the DB host and remembers the result.

    Some networks have slow or flaky DNS. libpq resolves the host on every new
    connection, so one bad lookup can stall a request for a minute. We resolve
    in a worker thread with a timeout, cache the IPv4 addresses, and fall back
    to the last good answer when a refresh fails. The hostname is still sent
    for TLS; only the TCP address comes from the cache (libpq `hostaddr`).
    """

    def __init__(self, host: str, port: int, ttl: float = 600, timeout: float = 4):
        self.host, self.port, self.ttl, self.timeout = host, port, ttl, timeout
        self._ips: list[str] = []
        self._fetched_at = 0.0
        self._lock = threading.Lock()

    def _lookup(self) -> list[str]:
        result: list[str] = []

        def work():
            try:
                infos = socket.getaddrinfo(self.host, self.port, socket.AF_INET, socket.SOCK_STREAM)
                result.extend(sorted({i[4][0] for i in infos}))
            except OSError:
                pass

        t = threading.Thread(target=work, daemon=True)
        t.start()
        t.join(self.timeout)
        return result

    def ip(self) -> str | None:
        with self._lock:
            if not self._ips or time.monotonic() - self._fetched_at > self.ttl:
                ips = self._lookup()
                # Nothing cached yet: retry, since failures on flaky DNS are usually transient.
                for _ in range(2):
                    if ips or self._ips:
                        break
                    ips = self._lookup()
                if ips:
                    self._ips, self._fetched_at = ips, time.monotonic()
                elif self._ips:
                    log.warning("DNS lookup for %s failed; using cached address", self.host)
                else:
                    log.warning("DNS lookup for %s failed and no cached address yet", self.host)
            return random.choice(self._ips) if self._ips else None


def make_engine(url: str):
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False}, pool_pre_ping=True)

    engine = create_engine(
        url,
        pool_pre_ping=True,  # replace connections the pooler has closed
        pool_size=5,
        max_overflow=5,
        pool_recycle=1800,
        pool_timeout=15,
        connect_args={
            "connect_timeout": 10,  # fail fast instead of hanging
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 3,
        },
    )
    parsed = make_url(url)
    if parsed.host and not parsed.host.replace(".", "").isdigit():
        resolver = CachedResolver(parsed.host, parsed.port or 5432)

        @event.listens_for(engine, "do_connect")
        def _use_cached_address(dialect, conn_rec, cargs, cparams):
            ip = resolver.ip()
            if ip:
                cparams["hostaddr"] = ip

    return engine


engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
