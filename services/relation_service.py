# app/services/relations.py
from __future__ import annotations

import uuid
from typing import List

from models.notes import Note
from models.relations import NoteRelation, RelationSuggestion

from core.db_client import get_session


def suggest_relations(embedding: List[float], limit: int = 5) -> List[RelationSuggestion]:
    distance_expr = Embedding.embedding.cosine_distance(embedding)

    with get_session() as db:
        q = (
            db.query(
                Note.id,
                Note.title,
                Note.summary,
                Note.status,
                (1 - distance_expr).label("score"),
            )
            .join(Embedding, Note.id == Embedding.note_id)
            .order_by(distance_expr)
            .limit(limit)
        )

        return [
            RelationSuggestion(
                note_id=str(row.id),
                title=row.title,
                summary=row.summary,
                status=row.status,
                score=float(row.score),
            )
            for row in q.all()
        ]


def suggest_relations_for_embedding(
    embedding: List[float],
    limit: int = 5,
) -> List[RelationSuggestion]:
    with get_session() as db:
        return suggest_relations(embedding, limit=limit)

def create_relation(
    source_note_id: str,
    target_note_id: str,
    relation_type: str,
    confidence: float | None = None,
) -> NoteRelation:
    with get_session() as db:
        relation = NoteRelation(
            id=uuid.uuid4(),
            source_note_id=source_note_id,
            target_note_id=target_note_id,
            relation_type=relation_type,
            confidence=confidence,
        )
        db.add(relation)
        db.commit()
        db.refresh(relation)
        return relation


def list_relations_for_note(note_id: str) -> List[NoteRelation]:
    """Alle relaties waarbij note_id bron of doel is."""
    with get_session() as db:
        return (
            db.query(NoteRelation)
            .filter(
                (NoteRelation.source_note_id == note_id)
                | (NoteRelation.target_note_id == note_id)
            )
            .all()
        )


def create_relation_entry(
    source_note_id: str,
    target_note_id: str,
    relation_type: str,
    confidence: float | None = None,
) -> NoteRelation:
    with get_session() as db:
        relation = create_relation(
            source_note_id=source_note_id,
            target_note_id=target_note_id,
            relation_type=relation_type,
            confidence=confidence,
        )

        db.expunge(relation)
        return relation
