from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from infrastructure.db import list_embeddings_snapshot, query_index, suggest_supersedes, upsert_entry
from infrastructure.llm import answer_from_context, summarize_and_tag

Match = Dict[str, Any]
Answer = Dict[str, Any]


@dataclass
class SaveResult:
    entry_id: Optional[str]
    summary: str
    tags: List[str]


class KnowledgeService:
    """Domain-layer façade that coordinates persistence and LLM helpers."""

    def search(self, question: str) -> Tuple[List[Match], Optional[Answer]]:
        question = (question or "").strip()
        if not question:
            return [], None

        res = query_index(question)
        matches = res.get("matches", [])
        if not matches:
            return [], None

        return matches, answer_from_context(question, matches)

    def suggest_relations(self, text: str) -> List[Match]:
        text = (text or "").strip()
        if not text:
            return []
        return suggest_supersedes(text)

    def save_entry(
        self,
        text: str,
        topic: str,
        created_by: str,
        related_ids: Iterable[str],
        supersedes_ids: Iterable[str],
    ) -> SaveResult:
        text = (text or "").strip()
        topic = (topic or "").strip()
        created_by = (created_by or "onbekend").strip() or "onbekend"

        summary_tags = summarize_and_tag(text)

        entry_id = upsert_entry(
            text=text,
            topic=topic,
            tags=summary_tags.get("tags", []),
            summary=summary_tags.get("summary", ""),
            created_by=created_by,
            related_to=_unique_ids(related_ids),
            supersedes=_unique_ids(supersedes_ids),
        )

        return SaveResult(
            entry_id=entry_id,
            summary=summary_tags.get("summary", ""),
            tags=list(summary_tags.get("tags", [])),
        )

    def list_documents(self) -> pd.DataFrame:
        return list_embeddings_snapshot()


def _unique_ids(ids: Iterable[str]) -> List[str]:
    seen = []
    for item in ids or []:
        item = (item or "").strip()
        if item and item not in seen:
            seen.append(item)
    return seen
