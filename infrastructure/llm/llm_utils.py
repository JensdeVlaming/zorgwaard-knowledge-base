from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import streamlit as st

from core.config import get_settings
from core.openai_client import get_openai_client

logger = logging.getLogger(__name__)
settings = get_settings()


# ----------------------------------------------------------------------
# Embeddings
# ----------------------------------------------------------------------
def embed_text(text: str) -> Optional[List[float]]:
    """Maak een embedding vector van tekst. Retourneert None bij lege input of fout."""
    text = (text or "").strip()
    if not text:
        return None
    return _cached_embed(settings.embed_model, text)


@st.cache_data(show_spinner=False)
def _cached_embed(model: str, text: str) -> Optional[List[float]]:
    try:
        client = get_openai_client()
        response = client.embeddings.create(input=text, model=model)
        return response.data[0].embedding
    except Exception as exc:  # pragma: no cover
        logger.exception("Embedding fout", exc_info=exc)
        st.error(f"Embedding fout: {exc}")
        return None


# ----------------------------------------------------------------------
# Chat (vrije tekst)
# ----------------------------------------------------------------------
def llm_chat(messages: List[Dict[str, str]], model: Optional[str] = None) -> str:
    """Vraag OpenAI om een antwoord in chat-format te genereren."""
    try:
        client = get_openai_client()
        response = client.chat.completions.create(
            model=model or settings.chat_model,
            messages=messages,
        )
        return response.choices[0].message.content
    except Exception as exc:  # pragma: no cover
        logger.exception("LLM fout", exc_info=exc)
        st.error(f"LLM fout: {exc}")
        return ""

# ----------------------------------------------------------------------
# Chat (structured output)
# ----------------------------------------------------------------------
def llm_chat_structured(messages: List[Dict[str, str]], schema: Any, model: Optional[str] = None) -> Any:
    """
    Vraag OpenAI om een antwoord in gestructureerd formaat (Pydantic schema).
    Voorbeeld:
        class Entities(BaseModel):
            entities: list[str]
        result = llm_chat_structured(msgs, Entities)
    """
    try:
        client = get_openai_client()
        response = client.chat.completions.parse(
            model=model or settings.chat_model,
            messages=messages,
            response_format=schema,
        )
        return response.choices[0].message.parsed   # <-- dit gebruiken
    except Exception as exc:  # pragma: no cover
        logger.exception("LLM structured fout", exc_info=exc)
        st.error(f"LLM structured fout: {exc}")
        return None
