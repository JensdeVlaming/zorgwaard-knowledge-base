# app/services/tags.py
from __future__ import annotations

import uuid
from typing import List

from sqlalchemy.orm import Session

from models.tag_model import NoteTag, Tag


def get_or_create_tag(db: Session, name: str) -> Tag:
    """Zoek of maak een Tag."""
    tag = db.query(Tag).filter(Tag.name == name).first()
    if tag:
        return tag
    tag = Tag(id=uuid.uuid4(), name=name)
    db.add(tag)
    db.flush()
    return tag


def link_tag_to_note(db: Session, note_id: uuid.UUID, tag: Tag) -> NoteTag:
    """Koppel een Tag aan een Note."""
    link = NoteTag(note_id=note_id, tag_id=tag.id)
    db.add(link)
    return link


def list_tags(db: Session, limit: int = 100) -> List[Tag]:
    return db.query(Tag).order_by(Tag.name.asc()).limit(limit).all()
