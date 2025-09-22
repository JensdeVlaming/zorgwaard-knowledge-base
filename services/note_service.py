from __future__ import annotations

import uuid
from typing import List, Optional, Tuple

from sqlalchemy.orm import joinedload

from core.db_client import get_session
from infrastructure.llm.llm_utils import embed_text
from models.embedding_model import Embedding
from models.entity_model import Entity, NoteEntity
from models.note_model import Note, NoteSearchResult
from models.tag_model import NoteTag, Tag


def create_note(
    title: str,
    content: str,
    summary: str,
    author: str,
    status: str = "draft",
    embedding: Optional[List[float]] = None,
    entities: Optional[List[dict]] = None,
    tags: Optional[List[str]] = None,
    embed_model: str = "text-embedding-3-large",
) -> Note:
    """
    Maak een nieuwe Note met optioneel embedding, entities en tags.
    """
    with get_session() as db:

        note = Note(
            id=uuid.uuid4(),
            title=title,
            content=content,
            summary=summary,
            author=author,
            status=status,
        )
        db.add(note)
        db.flush()  # nodig om note.id beschikbaar te maken

         # Embedding
        if embedding:
            emb = Embedding(
                note_id=note.id,
                model=embed_model,
                dim=len(embedding),
                embedding=embedding,
            )
            db.add(emb)

        # Entities
        if entities:
            for ent in entities:
                canonical = ent.get("canonical_value") or ent.get("value")
                entity = (
                    db.query(Entity)
                    .filter(
                        Entity.canonical_value == canonical,
                        Entity.entity_type == ent.get("entity_type"),
                    )
                    .first()
                )
                if not entity:
                    entity = Entity(
                        id=uuid.uuid4(),
                        entity_type=ent.get("entity_type", "onbekend"),
                        value=ent.get("value"),
                        canonical_value=canonical,
                    )
                    db.add(entity)
                    db.flush()
                link = NoteEntity(
                    note_id=note.id,
                    entity_id=entity.id,
                    role=ent.get("role"),
                )
                db.add(link)

        # Tags
        if tags:
            for tag_name in tags:
                tag = db.query(Tag).filter(Tag.name == tag_name).first()
                if not tag:
                    tag = Tag(id=uuid.uuid4(), name=tag_name)
                    db.add(tag)
                    db.flush()
                link = NoteTag(note_id=note.id, tag_id=tag.id)
                db.add(link)

        db.commit()
        db.refresh(note)
        return note

def list_notes(limit: int = 50) -> List[Note]:
    with get_session() as db:
        notes = (
            db.query(Note)
            .order_by(Note.created_at.desc())
            .limit(limit)
            .all()
        )

        for note in notes:
            db.expunge(note)

        return notes

def search_notes_by_similarity(
    embedding: List[float],
    *,
    limit: int = 5,
    entity_type: Optional[str] = None,
    entity_values: Optional[List[str]] = None,
) -> List[NoteSearchResult]:
    """Zoek notities op basis van embedding-similarity met optionele entiteitfilters."""

    if not embedding:
        return []

    max_candidates = max(limit * 4, limit)
    distance_expr = Embedding.embedding.cosine_distance(embedding)

    with get_session() as db:
        query = (
            db.query(Note, (1 - distance_expr).label("score"))
            .join(Embedding, Embedding.note_id == Note.id)
            .options(joinedload(Note.entities).joinedload(NoteEntity.entity))
            .filter(Note.status == "published")
            .order_by(distance_expr)
            .limit(max_candidates)
        )

        rows = query.all()
        results: List[NoteSearchResult] = []

        normalized_type = (entity_type or "").strip().lower()
        normalized_values = {
            value.strip().lower()
            for value in (entity_values or [])
            if value and value.strip()
        }

        for note, score in rows:
            if normalized_type:
                relevant_links = [
                    link
                    for link in note.entities
                    if link.entity
                    and (link.entity.entity_type or "").strip().lower() == normalized_type
                ]
                if not relevant_links:
                    continue

                if normalized_values:
                    note_values = {
                        (link.entity.canonical_value or link.entity.value or "")
                        .strip()
                        .lower()
                        for link in relevant_links
                    }
                    if not normalized_values.issubset(note_values):
                        continue

            results.append(
                NoteSearchResult(note=note, score=float(score) if score is not None else 0.0)
            )

            if len(results) >= limit:
                break

        return results


def search_question_matches(
    question: str,
    *,
    limit: int = 5,
    entity_type: Optional[str] = None,
    entity_values: Optional[List[str]] = None,
) -> Tuple[List[dict], List[NoteSearchResult]]:
    """Maak embedding voor een vraag en haal passende notities op met metadata."""

    question_clean = (question or "").strip()
    if not question_clean:
        raise ValueError("Vul een vraag in om te zoeken.")

    embedding = embed_text(question_clean)
    if not embedding:
        raise RuntimeError("Kon geen embedding maken voor deze vraag.")

    raw_results = search_notes_by_similarity(
        embedding,
        limit=limit,
        entity_type=entity_type,
        entity_values=entity_values,
    )

    matches: List[dict] = []
    detached_results: List[NoteSearchResult] = []

    for result in raw_results:
        note = result.note
        metadata = {
            "topic": note.title,
            "summary": note.summary,
            "status": note.status,
            "content": note.content,
            "entities": [
                {
                    "entity_type": link.entity.entity_type,
                    "value": link.entity.canonical_value or link.entity.value,
                }
                for link in note.entities
                if link.entity
            ],
        }

        matches.append(
            {
                "id": str(note.id),
                "score": result.score,
                "metadata": metadata,
            }
        )

        detached_results.append(NoteSearchResult(note=note, score=result.score))

    return matches, detached_results
