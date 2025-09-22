from __future__ import annotations

import uuid
from collections import defaultdict
from typing import List, Optional, Tuple

from sqlalchemy.orm import joinedload

from core.db_client import get_session
from infrastructure.llm.llm_utils import embed_text
from models.embedding_model import Embedding
from models.entity_model import Entity, NoteEntity
from models.note_model import Note, NoteSearchResult
from models.tag_model import NoteTag, Tag
from services.relation_service import list_relations_for_notes


def _format_timestamp(value) -> Optional[str]:
    if not value:
        return None
    try:
        return value.strftime("%d-%m-%Y %H:%M")
    except AttributeError:
        return str(value)


RELATION_DESCRIPTORS = {
    "supports": ("Ondersteunt", "Ondersteund door"),
    "contradicts": ("Spreekt tegen", "Wordt tegengesproken door"),
    "supersedes": ("Vervangt", "Vervangen door"),
    "related": ("Gerelateerd aan", "Gerelateerd aan"),
    "duplicate": ("Duplicaat van", "Duplicaat van"),
}


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


def get_note(note_id: str | uuid.UUID) -> Optional[Note]:
    """Haalt één notitie op uit de database en geeft deze los van de sessie terug."""
    if not note_id:
        return None

    try:
        parsed_id = uuid.UUID(str(note_id))
    except (TypeError, ValueError):
        return None

    with get_session() as db:
        note = db.query(Note).filter(Note.id == parsed_id).first()
        if note:
            db.expunge(note)
        return note


def delete_note(note_id: str | uuid.UUID) -> None:
    """Verwijdert een notitie en bijbehorende gegevens."""
    if not note_id:
        raise ValueError("note_id is verplicht")

    try:
        parsed_id = uuid.UUID(str(note_id))
    except (TypeError, ValueError) as exc:
        raise ValueError("Ongeldig note_id") from exc

    with get_session() as db:
        note = db.query(Note).filter(Note.id == parsed_id).first()
        if not note:
            raise ValueError("Notitie niet gevonden")

        db.delete(note)
        db.commit()


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

    note_ids = [
        str(result.note.id)
        for result in raw_results
        if getattr(result.note, "id", None)
    ]
    relation_context = _build_relation_metadata(note_ids)

    for result in raw_results:
        note = result.note
        metadata = {
            "topic": note.title,
            "summary": note.summary,
            "status": note.status,
            "created_at": _format_timestamp(note.created_at),
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

        relations_for_note = relation_context.get(str(note.id), [])
        if relations_for_note:
            metadata["relations"] = relations_for_note

        matches.append(
            {
                "id": str(note.id),
                "score": result.score,
                "metadata": metadata,
            }
        )

        detached_results.append(NoteSearchResult(note=note, score=result.score))

    return matches, detached_results


def _build_relation_metadata(note_ids: List[str]) -> dict[str, List[dict]]:
    relation_data: dict[str, List[dict]] = defaultdict(list)
    if not note_ids:
        return {}

    relations = list_relations_for_notes(note_ids)
    if not relations:
        return {}

    note_id_set = {str(note_id) for note_id in note_ids}

    for relation in relations:
        relation_type = (getattr(relation, "relation_type", "") or "").strip().lower()
        if relation_type not in RELATION_DESCRIPTORS:
            continue

        source_id = str(getattr(relation, "source_note_id", ""))
        target_id = str(getattr(relation, "target_note_id", ""))
        source_note = getattr(relation, "source_note", None)
        target_note = getattr(relation, "target_note", None)

        if source_id in note_id_set:
            descriptor = RELATION_DESCRIPTORS[relation_type][0]
            relation_data[source_id].append(
                {
                    "relation_type": relation_type,
                    "direction": "outgoing",
                    "descriptor": descriptor,
                    "other_id": target_id,
                    "other_title": getattr(target_note, "title", None),
                    "other_status": getattr(target_note, "status", None),
                    "other_created_at": _format_timestamp(
                        getattr(target_note, "created_at", None)
                    ),
                }
            )

        if target_id in note_id_set:
            descriptor = RELATION_DESCRIPTORS[relation_type][1]
            relation_data[target_id].append(
                {
                    "relation_type": relation_type,
                    "direction": "incoming",
                    "descriptor": descriptor,
                    "other_id": source_id,
                    "other_title": getattr(source_note, "title", None),
                    "other_status": getattr(source_note, "status", None),
                    "other_created_at": _format_timestamp(
                        getattr(source_note, "created_at", None)
                    ),
                }
            )

    return relation_data
