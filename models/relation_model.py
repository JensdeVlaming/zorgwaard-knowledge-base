from __future__ import annotations

import uuid
from datetime import datetime, timezone

from openai import BaseModel
from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from core.db_client import Base


class NoteRelation(Base):
    __tablename__ = "note_relations"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    source_note_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("notes.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_note_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("notes.id", ondelete="CASCADE"),
        nullable=False,
    )

    relation_type = Column(
        String,
        nullable=False,
    )  # supports | contradicts | supersedes | related | duplicate

    confidence = Column(Numeric(3, 2), nullable=True)

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("source_note_id", "target_note_id", name="uq_relation_pair"),
        CheckConstraint("source_note_id <> target_note_id", name="check_no_self_relation"),
    )

    # Relaties naar Note
    source_note = relationship("Note", foreign_keys=[source_note_id], backref="relations_out")
    target_note = relationship("Note", foreign_keys=[target_note_id], backref="relations_in")

class RelationSuggestion(BaseModel):
    note_id: str
    title: str
    summary: str
    status: str
    score: float