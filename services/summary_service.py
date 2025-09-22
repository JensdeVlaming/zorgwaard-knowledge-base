# app/services/summaries.py
from __future__ import annotations

from typing import List

from pydantic import BaseModel

from infrastructure.llm.llm_utils import llm_chat_structured


# ----------------------------------------------------------------------
# Structured output schema
# ----------------------------------------------------------------------
class SummaryResponse(BaseModel):
    summary: str


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------
def summarize(text: str, max_chars: int = 6000) -> str:
    """
    Vat tekst bondig samen. Grote teksten worden in chunks verwerkt.
    """
    chunks = _split_chunks(text, max_chars=max_chars)
    partials: List[str] = [_summarize_chunk(c) for c in chunks if c]

    if not partials:
        return ""

    if len(partials) == 1:
        return partials[0]

    return _combine_summaries(partials)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _split_chunks(text: str, max_chars: int = 6000) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: List[str] = []
    current = ""
    for p in paragraphs:
        if len(current) + len(p) + 2 <= max_chars:
            current = f"{current}\n\n{p}" if current else p
        else:
            if current:
                chunks.append(current)
            current = p
    if current:
        chunks.append(current)
    return chunks


def _summarize_chunk(chunk: str) -> str:
    parsed = llm_chat_structured(
        [
            {"role": "system", "content": "Vat bondig samen (zorgcontext)."},
            {"role": "user", "content": chunk},
        ],
        schema=SummaryResponse,
    )
    return parsed.summary.strip() if parsed else ""


def _combine_summaries(partials: List[str]) -> str:
    bullets = "\n".join(f"- {p}" for p in partials if p)
    parsed = llm_chat_structured(
        [
            {"role": "system", "content": "Combineer bullets tot één samenvatting (zorgcontext)."},
            {"role": "user", "content": bullets},
        ],
        schema=SummaryResponse,
    )
    return parsed.summary.strip() if parsed else bullets
