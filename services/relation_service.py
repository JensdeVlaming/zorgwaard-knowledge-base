# app/services/relations.py
from __future__ import annotations

import uuid
from typing import Iterable, List

from sqlalchemy.orm import joinedload, load_only

from core.db_client import get_session
from models.embedding_model import Embedding
from models.note_model import Note
from models.relation_model import NoteRelation, RelationSuggestion


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
    if not note_id:
        return []

    try:
        parsed_id = uuid.UUID(str(note_id))
    except (TypeError, ValueError):
        return []

    with get_session() as db:
        relations = (
            db.query(NoteRelation)
            .filter(
                (NoteRelation.source_note_id == parsed_id)
                | (NoteRelation.target_note_id == parsed_id)
            )
            .all()
        )

        for relation in relations:
            db.expunge(relation)

        return relations


def create_relation_entry(
    source_note_id: str,
    target_note_id: str,
    relation_type: str,
    confidence: float | None = None,
) -> NoteRelation:
    relation = create_relation(
        source_note_id=source_note_id,
        target_note_id=target_note_id,
        relation_type=relation_type,
        confidence=confidence,
    )

    # create_relation already commits and detaches the instance via expunge before returning
    return relation


def update_relation_type(relation_id: str, relation_type: str) -> NoteRelation:
    """Werk de relatie bij met een nieuw type en geef een gedetacheerde instantie terug."""
    if not relation_id:
        raise ValueError("relation_id is verplicht")

    try:
        parsed_id = uuid.UUID(str(relation_id))
    except (TypeError, ValueError) as exc:
        raise ValueError("Ongeldige relation_id") from exc

    normalized_type = (relation_type or "").strip()
    if not normalized_type:
        raise ValueError("relation_type is verplicht")

    with get_session() as db:
        relation = db.query(NoteRelation).filter(NoteRelation.id == parsed_id).first()
        if not relation:
            raise ValueError("Relatie niet gevonden")

        relation.relation_type = normalized_type
        db.commit()
        db.refresh(relation)
        db.expunge(relation)
        return relation


def delete_relation(relation_id: str) -> None:
    """Verwijder een relatie permanent."""
    if not relation_id:
        raise ValueError("relation_id is verplicht")

    try:
        parsed_id = uuid.UUID(str(relation_id))
    except (TypeError, ValueError) as exc:
        raise ValueError("Ongeldige relation_id") from exc

    with get_session() as db:
        relation = db.query(NoteRelation).filter(NoteRelation.id == parsed_id).first()
        if not relation:
            raise ValueError("Relatie niet gevonden")

        db.delete(relation)
        db.commit()


def list_relations_for_notes(note_ids: Iterable[str]) -> List[NoteRelation]:
    """Geef alle relaties terug waarbij een van de opgegeven notes betrokken is."""
    if not note_ids:
        return []

    try:
        normalized_ids = {uuid.UUID(str(note_id)) for note_id in note_ids}
    except (TypeError, ValueError):
        return []
    if not normalized_ids:
        return []

    with get_session() as db:
        relations = (
            db.query(NoteRelation)
            .options(
                joinedload(NoteRelation.source_note).options(
                    load_only(
                        Note.id, Note.title, Note.status, Note.summary, Note.created_at
                    )
                ),
                joinedload(NoteRelation.target_note).options(
                    load_only(
                        Note.id, Note.title, Note.status, Note.summary, Note.created_at
                    )
                ),
            )
            .filter(
                (NoteRelation.source_note_id.in_(normalized_ids))
                | (NoteRelation.target_note_id.in_(normalized_ids))
            )
            .all()
        )

        for relation in relations:
            db.expunge(relation)

        return relations
