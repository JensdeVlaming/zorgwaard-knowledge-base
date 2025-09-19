from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd
import streamlit as st

from core.config import get_settings, get_vector_index
from infrastructure.llm import embed_text

logger = logging.getLogger(__name__)

settings = get_settings()


@dataclass
class QueryOptions:
    top_k: int = 5
    expand_related: bool = True
    filter: Optional[Dict[str, Any]] = None


class VectorStore:
    """Pinecone-backed repository for knowledge vectors."""

    def __init__(self):
        self._index = get_vector_index()

    # Public API ---------------------------------------------------------
    def suggest_supersedes(self, text: str, threshold: float = 0.4, top_k: int = 5) -> List[Dict[str, Any]]:
        embedding = embed_text(text)
        if embedding is None:
            return []

        try:
            response = self._index.query(vector=embedding, top_k=top_k, include_metadata=True)
        except Exception as exc:  # pragma: no cover - relies on remote services
            logger.exception("Failed to query suggestions", exc_info=exc)
            st.warning(f"Suggestie-check fout: {exc}")
            return []

        return [
            {
                "id": match.get("id"),
                "score": match.get("score", 0.0),
                "metadata": match.get("metadata", {}),
            }
            for match in response.get("matches", [])
            if match.get("score", 0.0) >= threshold
        ]

    def upsert_entry(
        self,
        text: str,
        topic: str,
        tags: Iterable[str],
        summary: str,
        created_by: str,
        supersedes: Optional[Iterable[str]] = None,
        related_to: Optional[Iterable[str]] = None,
        entry_id: Optional[str] = None,
    ) -> Optional[str]:
        return _UpsertOperation(self._index).execute(
            text=text,
            topic=topic,
            tags=list(tags),
            summary=summary,
            created_by=created_by,
            supersedes=list(supersedes or []),
            related_to=list(related_to or []),
            entry_id=entry_id,
        )

    def query(self, question: str, *, options: QueryOptions | None = None) -> Dict[str, Any]:
        opts = options or QueryOptions()
        embedding = embed_text(question)
        if embedding is None:
            return {"matches": []}

        response = self._index.query(
            vector=embedding,
            top_k=opts.top_k,
            include_metadata=True,
            filter=opts.filter,
        )

        if not opts.expand_related:
            return response

        return _RelatedExpander(self._index).augment(response)

    def list_snapshot(self, limit: int = 2000) -> pd.DataFrame:
        stats = self._index.describe_index_stats()
        namespaces = stats.get("namespaces", {}) or {"": {"vector_count": stats.get("total_vector_count", 0)}}

        rows: list[dict[str, Any]] = []
        for namespace, meta in namespaces.items():
            count = meta.get("vector_count", 0)
            if count == 0:
                continue

            response = self._index.query(
                vector=[0.0] * settings.embed_dim,
                top_k=min(count, limit),
                namespace=namespace if namespace else None,
                include_metadata=True,
            )

            for match in response.get("matches", []):
                metadata = match.get("metadata", {}) or {}
                rows.append(
                    {
                        "ID": match.get("id", ""),
                        "Topic": metadata.get("topic", ""),
                        "Date": metadata.get("date", ""),
                        "Tags": metadata.get("tags", ""),
                        "Summary": metadata.get("summary", ""),
                        "Text": metadata.get("text", ""),
                        "Related_to": _split_ids(metadata.get("related_to")),
                        "Supersedes": _split_ids(metadata.get("supersedes")),
                        "Superseded_by": _split_ids(metadata.get("superseded_by")),
                        "Created_by": metadata.get("created_by", ""),
                    }
                )

        return pd.DataFrame(rows)


class _UpsertOperation:
    def __init__(self, index):
        self._index = index

    def execute(
        self,
        *,
        text: str,
        topic: str,
        tags: List[str],
        summary: str,
        created_by: str,
        supersedes: List[str],
        related_to: List[str],
        entry_id: Optional[str],
    ) -> Optional[str]:
        import uuid

        embedding = embed_text(text)
        if embedding is None:
            st.error("❌ Geen embedding gegenereerd.")
            return None

        entry_id = entry_id or str(uuid.uuid4())
        metadata = self._build_metadata(
            text=text,
            topic=topic,
            summary=summary,
            tags=tags,
            created_by=created_by,
            supersedes=supersedes,
            related_to=related_to,
        )

        self._index.upsert([(entry_id, embedding, metadata)])
        self._update_supersedes_links(entry_id, supersedes)
        self._update_related_links(entry_id, related_to)
        return entry_id

    def _build_metadata(
        self,
        *,
        text: str,
        topic: str,
        summary: str,
        tags: List[str],
        created_by: str,
        supersedes: List[str],
        related_to: List[str],
    ) -> Dict[str, Any]:
        metadata = {
            "topic": topic,
            "summary": summary,
            "tags": ",".join(tags),
            "date": datetime.now().isoformat(timespec="seconds"),
            "created_by": created_by,
            "text": text,
        }

        if related_to:
            metadata["related_to"] = ",".join(_unique_sorted(related_to))
        if supersedes:
            metadata["supersedes"] = ",".join(_unique_sorted(supersedes))
        return metadata

    def _update_supersedes_links(self, entry_id: str, supersedes: List[str]) -> None:
        for superseded_id in supersedes:
            try:
                existing = self._index.fetch(ids=[superseded_id])
                vector = existing.vectors.get(superseded_id)
                if not vector:
                    continue
                metadata = vector.metadata or {}
                superseded_by = _split_ids(metadata.get("superseded_by"))
                superseded_by.append(entry_id)
                metadata["superseded_by"] = ",".join(_unique_sorted(superseded_by))
                self._index.upsert([(superseded_id, vector.values, metadata)])
            except Exception as exc:  # pragma: no cover - depends on remote service
                logger.exception("Failed to update superseded_by", exc_info=exc)
                st.warning(f"Kon superseded_by niet instellen voor {superseded_id}: {exc}")

    def _update_related_links(self, entry_id: str, related_to: List[str]) -> None:
        for related_id in related_to:
            try:
                existing = self._index.fetch(ids=[related_id])
                vector = existing.vectors.get(related_id)
                if not vector:
                    continue
                metadata = vector.metadata or {}
                related = _split_ids(metadata.get("related_to"))
                related.append(entry_id)
                metadata["related_to"] = ",".join(_unique_sorted(related))
                self._index.upsert([(related_id, vector.values, metadata)])
            except Exception as exc:  # pragma: no cover - depends on remote service
                logger.exception("Failed to update related_to", exc_info=exc)
                st.warning(f"Kon related_to niet instellen voor {related_id}: {exc}")


class _RelatedExpander:
    def __init__(self, index):
        self._index = index

    def augment(self, response: Dict[str, Any]) -> Dict[str, Any]:
        matches = response.get("matches", [])
        if not matches:
            return response

        seen_ids = {match.get("id") for match in matches}
        extra_matches: list[dict[str, Any]] = []

        for match in matches:
            metadata = match.get("metadata", {}) or {}
            extra_matches.extend(
                self._load_relations(metadata=metadata, relation="related_to", seen_ids=seen_ids)
            )
            extra_matches.extend(
                self._load_relations(metadata=metadata, relation="supersedes", seen_ids=seen_ids)
            )
            extra_matches.extend(
                self._load_relations(metadata=metadata, relation="superseded_by", seen_ids=seen_ids)
            )

        response.setdefault("matches", []).extend(extra_matches)
        return response

    def _load_relations(self, *, metadata: Dict[str, Any], relation: str, seen_ids: set[str | None]) -> List[Dict[str, Any]]:
        identifiers = _split_ids(metadata.get(relation))
        collected: list[dict[str, Any]] = []

        for identifier in identifiers:
            if identifier in seen_ids:
                continue
            try:
                fetched = self._index.fetch(ids=[identifier])
            except Exception as exc:  # pragma: no cover - depends on remote service
                logger.exception("Failed to fetch related document", exc_info=exc)
                st.warning(f"Kon {relation} {identifier} niet ophalen: {exc}")
                continue

            for vector_id, vector in fetched.vectors.items():
                seen_ids.add(vector_id)
                collected.append(
                    {
                        "id": vector_id,
                        "metadata": vector.metadata or {},
                        "relation": relation,
                    }
                )

        return collected


def _split_ids(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _unique_sorted(items: Iterable[str]) -> List[str]:
    return sorted({item for item in items if item})


# Module-level façade to preserve existing API ---------------------------
_store = VectorStore()


def suggest_supersedes(text: str, threshold: float = 0.4, top_k: int = 5) -> List[Dict[str, Any]]:
    return _store.suggest_supersedes(text, threshold=threshold, top_k=top_k)


def upsert_entry(
    text: str,
    topic: str,
    tags: List[str],
    summary: str,
    created_by: str,
    supersedes: Optional[List[str]] = None,
    related_to: Optional[List[str]] = None,
    entry_id: Optional[str] = None,
):
    return _store.upsert_entry(
        text=text,
        topic=topic,
        tags=tags,
        summary=summary,
        created_by=created_by,
        supersedes=supersedes,
        related_to=related_to,
        entry_id=entry_id,
    )


def query_index(
    question: str,
    top_k: int = 5,
    filter: Optional[Dict[str, Any]] = None,
    expand_related: bool = True,
):
    return _store.query(question, options=QueryOptions(top_k=top_k, filter=filter, expand_related=expand_related))


def list_embeddings_snapshot(limit=2000) -> pd.DataFrame:
    return _store.list_snapshot(limit=limit)
