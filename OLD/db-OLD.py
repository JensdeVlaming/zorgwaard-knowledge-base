from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import (
    Session,
    aliased,
    declarative_base,
    relationship,
    selectinload,
)

from core.config import get_engine, get_session, get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

Base = declarative_base()


# ---------------------------------------------------------------------------
# ORM models
# ---------------------------------------------------------------------------


class Note(Base):
    __tablename__ = "notes"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    summary = Column(Text, nullable=False, default="")
    author_id = Column("author", Text, nullable=False)
    status = Column(Text, nullable=False, default=settings.default_note_status)
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)

    embedding = relationship(
        "Embedding", back_populates="note", uselist=False, cascade="all, delete-orphan"
    )
    outbound_relations = relationship(
        "NoteRelation",
        back_populates="source_note",
        cascade="all, delete-orphan",
        foreign_keys="NoteRelation.source_note_id",
    )
    inbound_relations = relationship(
        "NoteRelation",
        back_populates="target_note",
        foreign_keys="NoteRelation.target_note_id",
    )
    note_entities = relationship(
        "NoteEntity", back_populates="note", cascade="all, delete-orphan"
    )
    tags = relationship(
        "Tag", secondary="note_tags", back_populates="notes", lazy="selectin"
    )


class Embedding(Base):
    __tablename__ = "embeddings"

    note_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("notes.id", ondelete="CASCADE"),
        primary_key=True,
    )
    model = Column(Text, nullable=False)
    dim = Column(Integer, nullable=False)
    embedding = Column(Vector(settings.embed_dim), nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)

    note = relationship("Note", back_populates="embedding")


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
    relation_type = Column(Text, nullable=False)
    confidence = Column(Numeric(3, 2))
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)

    source_note = relationship(
        "Note", foreign_keys=[source_note_id], back_populates="outbound_relations"
    )
    target_note = relationship(
        "Note", foreign_keys=[target_note_id], back_populates="inbound_relations"
    )

    __table_args__ = (
        UniqueConstraint("source_note_id", "target_note_id", name="uq_note_relation"),
        CheckConstraint(
            "source_note_id <> target_note_id", name="ck_note_relation_no_self"
        ),
    )


class Entity(Base):
    __tablename__ = "entities"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type = Column(Text, nullable=False)
    value = Column(Text, nullable=False)
    canonical_value = Column(Text)
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)

    note_entities = relationship("NoteEntity", back_populates="entity")


class NoteEntity(Base):
    __tablename__ = "note_entities"

    note_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("notes.id", ondelete="CASCADE"),
        primary_key=True,
    )
    entity_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role = Column(Text)
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)

    note = relationship("Note", back_populates="note_entities")
    entity = relationship("Entity", back_populates="note_entities")


class Tag(Base):
    __tablename__ = "tags"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False, unique=True)

    notes = relationship(
        "Note", secondary="note_tags", back_populates="tags", lazy="selectin"
    )


class NoteTag(Base):
    __tablename__ = "note_tags"

    note_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("notes.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    )

# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------


@dataclass
class EntityRecord:
    id: str
    label: str
    entity_type: str
    canonical_value: Optional[str]


@dataclass
class NoteEntityRecord:
    entity: EntityRecord
    role: Optional[str]


@dataclass
class RelationRecord:
    id: str
    relation_type: str
    target_id: str
    target_title: str
    target_status: str


@dataclass
class NoteRecord:
    id: str
    title: str
    content: str
    summary: Optional[str]
    tags: List[str]
    author_id: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass
class NoteDetail:
    note: NoteRecord
    relations: List[RelationRecord]
    entities: List[NoteEntityRecord]


@dataclass
class SearchMatch:
    note: NoteRecord
    score: Optional[float]
    relation: Optional[str]
    relations: Dict[str, List[str]]


RELATION_TYPES = ["related", "supports", "contradicts", "supersedes", "duplicate"]
SEARCH_RELATED_TYPES = ["supports", "contradicts", "related"]
STATUS_MAP = {
    "Draft": "draft",
    "Published": "published",
    "Archived": "archived",
}


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------


def ensure_schema() -> None:
    engine = get_engine()
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_notes_status_updated ON notes(status, updated_at DESC)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_relations_source ON note_relations(source_note_id)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_relations_target ON note_relations(target_note_id)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_relations_type ON note_relations(relation_type)"
            )
        )
        try:
            conn.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS idx_embeddings_cosine
                    ON embeddings USING ivfflat (embedding vector_cosine_ops)
                    WITH (lists = 100)
                    """
                )
            )
        except Exception as exc:  # pragma: no cover - depends on server capabilities
            logger.warning("Kon ivfflat-index niet aanmaken: %s", exc)


# ---------------------------------------------------------------------------
# Entity helpers
# ---------------------------------------------------------------------------


def list_entities() -> List[EntityRecord]:
    with get_session() as session:
        rows = (
            session.execute(
                select(Entity).order_by(
                    func.lower(Entity.entity_type), func.lower(Entity.value)
                )
            )
            .scalars()
            .all()
        )
        return [_serialize_entity(row) for row in rows]


def ensure_entities(entities: Sequence[Dict[str, str]]) -> List[EntityRecord]:
    if not entities:
        return []

    normalized: List[Tuple[str, str, str]] = []
    for item in entities:
        value = item.get("value", "").strip()
        if not value:
            continue
        entity_type = item.get("entity_type", "onbekend").strip() or "onbekend"
        canonical = item.get("canonical_value") or value
        normalized.append((entity_type, value, canonical.strip().lower()))

    if not normalized:
        return []

    created: List[EntityRecord] = []
    with get_session() as session:
        canonical_values = tuple({c for _, _, c in normalized})
        if canonical_values:
            existing = (
                session.execute(
                    select(Entity).where(
                        or_(
                            func.lower(Entity.canonical_value).in_(canonical_values),
                            func.lower(Entity.value).in_(canonical_values),
                        )
                    )
                )
                .scalars()
                .all()
            )
        else:
            existing = []
        existing_map = {
            (e.canonical_value.lower() if e.canonical_value else e.value.lower()): e
            for e in existing
        }

        for entity_type, value, canonical in normalized:
            entity = existing_map.get(canonical)
            if not entity:
                entity = Entity(
                    entity_type=entity_type, value=value, canonical_value=canonical
                )
                session.add(entity)
                session.flush()
                existing_map[canonical] = entity
            created.append(_serialize_entity(entity))
    return created


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------


def list_note_options(term: str, limit: int = 20) -> List[Dict[str, str]]:
    pattern = f"%{term.lower()}%" if term else None
    with get_session() as session:
        stmt = (
            select(Note.id, Note.title, Note.status).order_by(Note.title).limit(limit)
        )
        if pattern:
            stmt = stmt.where(func.lower(Note.title).like(pattern))
        rows = session.execute(stmt).all()
    return [
        {
            "id": str(row.id),
            "title": row.title,
            "status": row.status,
        }
        for row in rows
    ]


def list_all_notes(limit: int = 100) -> List[NoteRecord]:
    """List all notes with basic information, ordered by creation date."""
    with get_session() as session:
        rows = (
            session.execute(
                select(Note)
                .options(selectinload(Note.tags))
                .order_by(Note.created_at.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [_serialize_note(row) for row in rows]


def list_all_relations(limit: int = 200) -> List[Dict[str, str]]:
    """List all note relations with source and target information."""
    with get_session() as session:
        target_note = aliased(Note, name="target")
        rows = session.execute(
            select(
                NoteRelation.id,
                NoteRelation.relation_type,
                NoteRelation.source_note_id,
                NoteRelation.target_note_id,
                Note.title.label("source_title"),
                Note.summary.label("source_summary"),  # toegevoegd
                Note.status.label("source_status"),
                target_note.title.label("target_title"),
                target_note.summary.label("target_summary"),  # toegevoegd
                target_note.status.label("target_status"),
            )
            .join(Note, NoteRelation.source_note_id == Note.id)
            .join(target_note, NoteRelation.target_note_id == target_note.id)
            .order_by(NoteRelation.relation_type, Note.title)
            .limit(limit)
        ).all()

        return [
            {
                "id": str(row.id),
                "relation_type": row.relation_type,
                "source_id": str(row.source_note_id),
                "source_title": row.source_title,
                "source_summary": row.source_summary,
                "source_status": row.source_status,
                "target_id": str(row.target_note_id),
                "target_title": row.target_title,
                "target_summary": row.target_summary,
                "target_status": row.target_status,
            }
            for row in rows
        ]


def create_note(
    *,
    title: str,
    content: str,
    author_id: str,
    status: str,
    tags: List[str],
    summary: Optional[str],
    embedding: Sequence[float],
    relations: Sequence[Tuple[str, uuid.UUID]],
    entity_ids: Sequence[uuid.UUID],
) -> NoteDetail:
    note_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    with get_session() as session:
        note = Note(
            id=note_id,
            title=title,
            content=content,
            summary=(summary or ""),
            author_id=author_id,
            status=status,
            created_at=now,
            updated_at=now,
        )

        note.tags = _ensure_tags(session, tags)

        session.add(note)
        session.flush()

        note.embedding = Embedding(
            note_id=note.id,
            model=settings.embed_model,
            dim=settings.embed_dim,
            embedding=list(embedding),
            created_at=now,
            updated_at=now,
        )

        if entity_ids:
            rows = (
                session.execute(select(Entity).where(Entity.id.in_(entity_ids)))
                .scalars()
                .all()
            )
            for entity in rows:
                note.note_entities.append(NoteEntity(entity=entity))

        for relation_type, target_id in relations:
            note.outbound_relations.append(
                NoteRelation(
                    id=uuid.uuid4(),
                    source_note_id=note.id,
                    target_note_id=target_id,
                    relation_type=relation_type,
                    confidence=1.0,
                    created_at=now,
                    updated_at=now,
                )
            )
            if relation_type == "supersedes":
                session.execute(
                    update(Note)
                    .where(Note.id == target_id)
                    .values(status="archived", updated_at=now)
                )

    return get_note_detail(note_id)


def _ensure_tags(session: Session, tag_names: Sequence[str]) -> List[Tag]:
    cleaned = [(tag or "").strip() for tag in tag_names or [] if (tag or "").strip()]
    if not cleaned:
        return []

    lookup = {name.lower(): name for name in cleaned}
    existing = (
        session.execute(
            select(Tag).where(func.lower(Tag.name).in_(tuple(lookup.keys())))
        )
        .scalars()
        .all()
    )
    existing_map = {tag.name.lower(): tag for tag in existing}

    tags: List[Tag] = []
    for name in cleaned:
        key = name.lower()
        tag_obj = existing_map.get(key)
        if not tag_obj:
            tag_obj = Tag(id=uuid.uuid4(), name=lookup[key])
            session.add(tag_obj)
            session.flush([tag_obj])
            existing_map[key] = tag_obj
        tags.append(tag_obj)
    return tags


def get_note_detail(note_id: uuid.UUID) -> NoteDetail:
    with get_session() as session:
        note = session.execute(
            select(Note)
            .options(
                selectinload(Note.outbound_relations).selectinload(
                    NoteRelation.target_note
                ),
                selectinload(Note.note_entities).selectinload(NoteEntity.entity),
                selectinload(Note.tags),
            )
            .where(Note.id == note_id)
        ).scalar_one()
        return _serialize_note_detail(note)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def search_similar_notes(
    *,
    query_vector: Sequence[float],
    entity_filter_ids: Sequence[uuid.UUID],
    top_k: int = 5,
    related_limit: int = 3,
) -> List[SearchMatch]:
    with get_session() as session:
        sup_alias = aliased(NoteRelation)
        stmt = (
            select(
                Note,
                Embedding.embedding.cosine_distance(list(query_vector)).label(
                    "distance"
                ),
            )
            .join(Embedding, Embedding.note_id == Note.id)
            .outerjoin(
                sup_alias,
                (sup_alias.target_note_id == Note.id)
                & (sup_alias.relation_type == "supersedes"),
            )
            .where(sup_alias.id.is_(None))
            .where(func.lower(Note.status) == "published")
            .order_by(Embedding.embedding.cosine_distance(list(query_vector)))
            .limit(top_k)
        )
        if entity_filter_ids:
            stmt = stmt.join(NoteEntity, NoteEntity.note_id == Note.id).where(
                NoteEntity.entity_id.in_(entity_filter_ids)
            )

        rows = session.execute(stmt).all()
        if not rows:
            return []

        base_ids = [row.Note.id for row in rows]
        notes_map = _load_notes(session, base_ids)
        relations_map = _load_relations(session, base_ids)

        matches: List[SearchMatch] = []
        for row in rows:
            note = notes_map[row.Note.id]
            matches.append(
                SearchMatch(
                    note=_serialize_note(note),
                    score=_distance_to_score(row.distance),
                    relation=None,
                    relations=relations_map.get(str(note.id), {}),
                )
            )

        # expand with related notes (supports/contradicts/related)
        related_ids: Dict[str, str] = {}
        for row in notes_map.values():
            for rel in row.outbound_relations:
                if (
                    rel.relation_type in SEARCH_RELATED_TYPES
                    and str(rel.target_note_id) not in related_ids
                ):
                    related_ids[str(rel.target_note_id)] = rel.relation_type
        if related_ids:
            related_note_ids = list(related_ids.keys())[: related_limit * len(base_ids)]
            extra_map = _load_notes(
                session, [uuid.UUID(rid) for rid in related_note_ids]
            )
            extra_relations = _load_relations(
                session, [uuid.UUID(rid) for rid in related_note_ids]
            )
            for rid, relation_type in related_ids.items():
                note_obj = extra_map.get(uuid.UUID(rid))
                if not note_obj:
                    continue
                matches.append(
                    SearchMatch(
                        note=_serialize_note(note_obj),
                        score=None,
                        relation=relation_type,
                        relations=extra_relations.get(rid, {}),
                    )
                )

        return matches


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _load_notes(
    session: Session, note_ids: Sequence[uuid.UUID]
) -> Dict[uuid.UUID, Note]:
    if not note_ids:
        return {}
    rows = (
        session.execute(
            select(Note)
            .options(
                selectinload(Note.note_entities).selectinload(NoteEntity.entity),
                selectinload(Note.outbound_relations),
                selectinload(Note.tags),
            )
            .where(Note.id.in_(note_ids))
        )
        .scalars()
        .all()
    )
    return {row.id: row for row in rows}


def _load_relations(
    session: Session, note_ids: Sequence[uuid.UUID]
) -> Dict[str, Dict[str, List[str]]]:
    if not note_ids:
        return {}
    rows = (
        session.execute(
            select(NoteRelation).where(NoteRelation.source_note_id.in_(note_ids))
        )
        .scalars()
        .all()
    )
    relations: Dict[str, Dict[str, List[str]]] = {}
    for rel in rows:
        sid = str(rel.source_note_id)
        relations.setdefault(sid, {}).setdefault(rel.relation_type, []).append(
            str(rel.target_note_id)
        )
        if rel.relation_type == "supersedes":
            relations.setdefault(str(rel.target_note_id), {}).setdefault(
                "superseded_by", []
            ).append(sid)
    for rel_map in relations.values():
        for key in rel_map:
            rel_map[key] = sorted(set(rel_map[key]))
    return relations


def _serialize_note_detail(note: Note) -> NoteDetail:
    return NoteDetail(
        note=_serialize_note(note),
        relations=[
            RelationRecord(
                id=str(rel.id),
                relation_type=rel.relation_type,
                target_id=str(rel.target_note_id),
                target_title=rel.target_note.title if rel.target_note else "",
                target_status=rel.target_note.status if rel.target_note else "",
            )
            for rel in note.outbound_relations
        ],
        entities=[
            NoteEntityRecord(entity=_serialize_entity(ne.entity), role=ne.role)
            for ne in note.note_entities
        ],
    )


def _serialize_note(note: Note) -> NoteRecord:
    return NoteRecord(
        id=str(note.id),
        title=note.title,
        content=note.content,
        summary=note.summary,
        tags=list(note.tags or []),
        author_id=note.author_id,
        status=note.status,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


def _serialize_entity(entity: Entity) -> EntityRecord:
    return EntityRecord(
        id=str(entity.id),
        label=entity.value,
        entity_type=entity.entity_type,
        canonical_value=entity.canonical_value,
    )


def _distance_to_score(distance: Optional[float]) -> Optional[float]:
    if distance is None:
        return None
    return max(0.0, 1.0 - float(distance))
