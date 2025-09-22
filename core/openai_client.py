from __future__ import annotations

from openai import OpenAI

from core.config import get_settings

_client: OpenAI | None = None

def get_openai_client() -> OpenAI:
    """
    Geef een singleton OpenAI-client die de API key uit settings gebruikt.
    """
    global _client
    if _client is None:
        settings = get_settings()
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client
