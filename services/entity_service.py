# app/services/entities.py
from __future__ import annotations

from typing import List

from core.db_client import get_session
from models.entity_model import Entity


def list_entities(limit: int = 100) -> List[Entity]:
    db = get_session()

    try:
        entities = (
            db.query(Entity)
            .order_by(Entity.created_at.desc())
            .limit(limit)
            .all()
        )

        for entity in entities:
            db.expunge(entity)

        return entities
    finally:
        db.close()
