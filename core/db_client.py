from __future__ import annotations

import logging
import threading
import time

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, scoped_session, sessionmaker

from core.config import get_settings
from infrastructure.migrations.runner import run_pending_migrations

logger = logging.getLogger(__name__)

# Declarative base voor modellen
Base = declarative_base()

# -------------------------------------------------------
# Engine & Session configuratie
# -------------------------------------------------------
settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,       # check verbindingen voordat ze gebruikt worden
    pool_size=5,              # max aantal actieve connecties
    max_overflow=10,          # extra connecties als pool vol zit
    future=True,              # moderne SQLAlchemy API
)

SessionLocal = scoped_session(
    sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
)

_db_ready = False
_db_ready_lock = threading.Lock()


# -------------------------------------------------------
# Helpers
# -------------------------------------------------------


def _wait_for_database(max_attempts: int = 6, initial_delay: float = 1.0) -> None:
    """Block until the database accepts connections or retries are exhausted."""

    global _db_ready

    if _db_ready:
        return

    with _db_ready_lock:
        if _db_ready:
            return

        delay = initial_delay
        for attempt in range(1, max_attempts + 1):
            try:
                with engine.connect() as connection:
                    connection.execute(text("SELECT 1"))
                _db_ready = True
                return
            except OperationalError as exc:  # database still warming up
                engine.dispose()  # drop broken connections from the pool
                if attempt == max_attempts:
                    logger.error(
                        "Database did not become ready after %s attempts", attempt
                    )
                    raise
                logger.warning(
                    "Database not ready yet (attempt %s/%s): %s",
                    attempt,
                    max_attempts,
                    exc,
                )
                time.sleep(delay)
                delay *= 2


def get_session():
    """Return a new SQLAlchemy Session (scoped)."""
    _wait_for_database()
    return SessionLocal()


def init_db():
    _wait_for_database()
    run_pending_migrations(engine)
    logger.info("Database migrations executed.")
