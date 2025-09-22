from __future__ import annotations

import uuid

from sqlalchemy import Column, ForeignKey, PrimaryKeyConstraint, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from core.db_client import Base


class Tag(Base):
    __tablename__ = "tags"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False)

    notes = relationship("NoteTag", back_populates="tag")


class NoteTag(Base):
    __tablename__ = "note_tags"

    note_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("notes.id", ondelete="CASCADE"),
        nullable=False,
    )
    tag_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("tags.id", ondelete="CASCADE"),
        nullable=False,
    )

    __table_args__ = (
        PrimaryKeyConstraint("note_id", "tag_id", name="pk_note_tag"),
    )

    note = relationship(
        "Note",
        back_populates="tags",
        passive_deletes=True,
    )
    tag = relationship(
        "Tag",
        back_populates="notes",
        passive_deletes=True,
    )
