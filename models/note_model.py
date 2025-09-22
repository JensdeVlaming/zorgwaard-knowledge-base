from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from core.db_client import Base


class Note(Base):
    __tablename__ = "notes"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    summary = Column(Text, nullable=False)
    author = Column(String, nullable=False)
    status = Column(
        String,
        default="draft",
        nullable=False,
    )
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relaties
    embedding = relationship("Embedding", back_populates="note", uselist=False)
    entities = relationship("NoteEntity", back_populates="note")
    tags = relationship("NoteTag", back_populates="note")

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','published','archived')",
            name="check_status_valid",
        ),
    )


@dataclass
class NoteSearchResult:
    note: "Note"
    score: float
