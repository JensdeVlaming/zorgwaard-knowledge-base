from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

# laad .env automatisch als aanwezig
load_dotenv()


class Settings:
    # Database
    database_url: str

    # OpenAI
    openai_api_key: str
    embed_model: str = "text-embedding-3-large"
    chat_model: str = "gpt-4o-mini"

    # Embedding dimensie (afhankelijk van model)
    @property
    def embed_dim(self) -> int:
        if self.embed_model == "text-embedding-3-large":
            return 3072
        if self.embed_model == "text-embedding-3-small":
            return 1536
        return 1536  # fallback


def _require_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"Omgevingsvariabele {key} is niet gezet")
    return value


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.database_url = _require_env("DATABASE_URL")
    s.openai_api_key = _require_env("OPENAI_API_KEY")
    s.embed_model = os.getenv("EMBED_MODEL", s.embed_model)
    s.chat_model = os.getenv("CHAT_MODEL", s.chat_model)
    return s
