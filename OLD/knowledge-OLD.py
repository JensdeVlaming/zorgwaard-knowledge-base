from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from infrastructure.db import (
    RELATION_TYPES,
    STATUS_MAP,
    EntityRecord,
    NoteDetail,
    NoteRecord,
    SearchMatch,
    create_note,
    ensure_entities,
    ensure_schema,
    get_note_detail,
    list_all_notes,
    list_all_relations,
    list_entities,
    list_note_options,
    search_similar_notes,
)
from infrastructure.llm import (
    answer_from_context,
    embed_text,
    suggest_entities,
    summarize_and_tag,
)


@dataclass
class EnrichmentResult:
    summary: str
    tags: List[str]
    entities: List[EntityRecord]


@dataclass
class SaveNoteResult:
    detail: NoteDetail


@dataclass
class ChatResult:
    answer: str
    matches: List[SearchMatch]
    raw_matches: List[Dict[str, Any]]
    trace: Dict[str, Any]


class KnowledgeService:
    """Façade that orchestrates database and LLM interactions for the UI."""

    def __init__(self) -> None:
        ensure_schema()

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------
    def status_options(self) -> Dict[str, str]:
        return STATUS_MAP.copy()

    def relation_types(self) -> List[str]:
        return RELATION_TYPES.copy()

    def list_entities(self) -> List[EntityRecord]:
        return list_entities()

    def list_note_options(self, term: str) -> List[Dict[str, str]]:
        return list_note_options(term)

    def list_all_notes(self, limit: int = 100) -> List[NoteRecord]:
        """List all notes with basic information."""
        return list_all_notes(limit)

    def list_all_relations(self, limit: int = 200) -> List[Dict[str, str]]:
        """List all note relations with source and target information."""
        return list_all_relations(limit)

    # ------------------------------------------------------------------
    # Enrichment helpers
    # ------------------------------------------------------------------
    def generate_enrichment(self, content: str) -> EnrichmentResult:
        enrichment = summarize_and_tag(content)
        entity_suggestions = suggest_entities(content)
        ensured_entities = ensure_entities(entity_suggestions)
        return EnrichmentResult(
            summary=enrichment.get("summary", ""),
            tags=enrichment.get("tags", []),
            entities=ensured_entities,
        )

    def suggest_relations(self, content: str, limit: int = 5) -> List[SearchMatch]:
        """Suggest related notes for the current draft content."""
        cleaned_content = (content or "").strip()
        if not cleaned_content:
            return []

        embedding = embed_text(cleaned_content)
        if embedding is None:
            return []

        return search_similar_notes(
            query_vector=embedding,
            entity_filter_ids=[],
            top_k=limit,
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def save_note(
        self,
        *,
        title: str,
        content: str,
        author: str,
        status_label: str,
        tags: Iterable[str],
        relations: Sequence[Dict[str, str]],
        entity_ids: Sequence[str],
    ) -> SaveNoteResult:
        note_title = title.strip()
        note_content = content.strip()
        if not note_title or not note_content:
            raise ValueError("Titel en inhoud zijn verplicht")

        author_id = (author or self.default_author()).strip() or "onbekend"
        status_value = STATUS_MAP.get(status_label, status_label.lower())
        tag_list = _normalise_tags(tags)

        summary_payload = summarize_and_tag(note_content)
        summary_text = summary_payload.get("summary")
        tag_list = _merge_tags(tag_list, summary_payload.get("tags", []))

        embedding = embed_text(note_content)
        if embedding is None:
            raise RuntimeError("Geen embedding gegenereerd")

        relation_entries = _normalise_relations(relations)
        entity_uuid_list = [uuid.UUID(value) for value in entity_ids if value]

        detail = create_note(
            title=note_title,
            content=note_content,
            author_id=author_id,
            status=status_value,
            tags=tag_list,
            summary=summary_text,
            embedding=embedding,
            relations=relation_entries,
            entity_ids=entity_uuid_list,
        )

        return SaveNoteResult(detail=detail)

    def load_note(self, note_id: str) -> NoteDetail:
        return get_note_detail(uuid.UUID(note_id))

    # ------------------------------------------------------------------
    # Search / chat
    # ------------------------------------------------------------------
    def chat(
        self, question: str, entity_ids: Sequence[str], top_k: int = 5
    ) -> ChatResult:
        cleaned_question = (question or "").strip()
        if not cleaned_question:
            raise ValueError("Voer een vraag in")

        embedding = embed_text(cleaned_question)
        if embedding is None:
            raise RuntimeError("Geen embedding gegenereerd")

        entity_uuid_filter = [uuid.UUID(value) for value in entity_ids if value]
        matches = search_similar_notes(
            query_vector=embedding,
            entity_filter_ids=entity_uuid_filter,
            top_k=top_k,
        )
        if not matches:
            return ChatResult(answer="", matches=[], raw_matches=[], trace={})

        llm_payload = _build_llm_payload(matches)
        llm_answer = answer_from_context(cleaned_question, llm_payload)
        return ChatResult(
            answer=llm_answer.get("answer", ""),
            matches=matches,
            raw_matches=llm_payload,
            trace=llm_answer.get("trace", {}),
        )


# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------


def _normalise_tags(tags: Iterable[str]) -> List[str]:
    unique: List[str] = []
    seen: set[str] = set()
    for tag in tags or []:
        cleaned = tag.strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key not in seen:
            unique.append(cleaned)
            seen.add(key)
    return unique


def _merge_tags(existing: List[str], extra: Iterable[str]) -> List[str]:
    seen = {tag.lower(): tag for tag in existing}
    for tag in extra or []:
        cleaned = tag.strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key not in seen:
            seen[key] = cleaned
    return list(seen.values())


def _normalise_relations(
    relations: Sequence[Dict[str, str]],
) -> List[Tuple[str, uuid.UUID]]:
    normalised: List[Tuple[str, uuid.UUID]] = []
    for relation in relations or []:
        relation_type = relation.get("relation_type") or relation.get("type")
        target_id = relation.get("target_id") or relation.get("target")
        if not relation_type or not target_id:
            continue
        try:
            normalised.append((relation_type, uuid.UUID(target_id)))
        except ValueError:
            continue
    return normalised


def _build_llm_payload(matches: Sequence[SearchMatch]) -> List[Dict[str, Any]]:
    payload: List[Dict[str, Any]] = []
    for match in matches:
        metadata = {
            "topic": match.note.title,
            "summary": match.note.summary or "",
            "tags": ", ".join(match.note.tags),
            "date": match.note.created_at.isoformat(timespec="seconds"),
            "created_by": match.note.author_id or "",
            "status": match.note.status,
            "text": match.note.content,
        }

        for relation_key, targets in (match.relations or {}).items():
            metadata[relation_key] = ",".join(targets)
        payload.append(
            {
                "id": match.note.id,
                "score": match.score if match.score is not None else 0.0,
                "metadata": metadata,
                "relation": match.relation,
            }
        )
    return payload
