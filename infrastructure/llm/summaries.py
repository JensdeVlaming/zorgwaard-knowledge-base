from __future__ import annotations

from typing import List

from pydantic import BaseModel

from infrastructure.llm.llm_utils import llm_chat_structured


# ----------------------------------------------------------------------
# Pydantic schema voor structured output
# ----------------------------------------------------------------------
class SummaryResponse(BaseModel):
    summary: str


# ----------------------------------------------------------------------
# Samenvatten van documenten
# ----------------------------------------------------------------------
def summarize(text: str, max_chars: int = 6000) -> str:
    """
    Vat tekst bondig samen met de LLM.
    Bij lange teksten: splitsen in chunks en daarna combineren.
    """
    chunks = _split_chunks(text, max_chars=max_chars)
    partials: List[str] = []

    for chunk in chunks:
        summary = _summarize_chunk(chunk)
        if summary:
            partials.append(summary)

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
    system_prompt = {"role": "system", "content": "Vat bondig samen in zorg en IT context."}
    user_prompt = {"role": "user", "content": chunk}

    parsed: SummaryResponse | None = llm_chat_structured(
        [system_prompt, user_prompt], schema=SummaryResponse
    )
    return parsed.summary.strip() if parsed else ""


def _combine_summaries(partials: List[str]) -> str:
    bullets = "\n".join(f"- {p}" for p in partials if p)
    system_prompt = {"role": "system", "content": "Combineer bullets tot één samenvatting in zorg en IT context."}
    user_prompt = {"role": "user", "content": bullets}

    parsed: SummaryResponse | None = llm_chat_structured(
        [system_prompt, user_prompt], schema=SummaryResponse
    )
    return parsed.summary.strip() if parsed else bullets
