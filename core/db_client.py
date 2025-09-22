from __future__ import annotations

import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, scoped_session, sessionmaker

from core.config import get_settings

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
    """Geef een nieuwe SQLAlchemy Session (scoped)."""
    return SessionLocal()


def init_db():
    # importeer modellen zodat Base.metadata gevuld wordt
    import models.entities  # noqa: F401
    import models.notes  # noqa: F401
    import models.relations  # noqa: F401
    import models.tags  # noqa: F401

    Base.metadata.create_all(bind=engine)
    logger.info("Database tabellen aangemaakt.")
