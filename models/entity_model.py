from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, PrimaryKeyConstraint, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from core.db_client import Base


class Entity(Base):
    __tablename__ = "entities"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type = Column(String, nullable=False)   # bv. app, proces, rol, locatie
    value = Column(Text, nullable=False)           # ruwe waarde uit tekst
    canonical_value = Column(Text, nullable=True)  # genormaliseerd

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    notes = relationship(
        "NoteEntity",
        back_populates="entity",
        passive_deletes=True,
    )


class NoteEntity(Base):
    __tablename__ = "note_entities"

    note_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("notes.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    role = Column(String, nullable=True)  # bv. onderwerp, actor, tool

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        PrimaryKeyConstraint("note_id", "entity_id", name="pk_note_entity"),
    )

    note = relationship(
        "Note",
        back_populates="entities",
        passive_deletes=True,
    )
    entity = relationship(
        "Entity",
        back_populates="notes",
        passive_deletes=True,
    )
