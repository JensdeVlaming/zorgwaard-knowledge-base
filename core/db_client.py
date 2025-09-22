from __future__ import annotations

import logging

from sqlalchemy import create_engine
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


# -------------------------------------------------------
# Helpers
# -------------------------------------------------------
def get_session():
    """Return a new SQLAlchemy Session (scoped)."""
    return SessionLocal()


def init_db():
    run_pending_migrations(engine)
    logger.info("Database migrations executed.")
