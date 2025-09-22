from __future__ import annotations

import os
from functools import lru_cache
from urllib.parse import urlparse

from dotenv import load_dotenv

# laad .env automatisch als aanwezig
load_dotenv()


class Settings:
    # Database
    db_name: str = "knowledge_base"
    db_user: str
    db_password: str
    db_host: str = "localhost"
    db_port: int = 5432
    database_url_override: str | None = None

    # OpenAI
    openai_api_key: str
    embed_model: str = "text-embedding-3-large"
    chat_model: str = "gpt-4o-mini"

    @property
    def embed_dim(self) -> int:
        if self.embed_model == "text-embedding-3-large":
            return 3072
        if self.embed_model == "text-embedding-3-small":
            return 1536
        return 1536  # fallback

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"


def _require_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"Environment variable {key} is not set")
    return value


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    database_url = os.getenv("DATABASE_URL")

    if database_url:
        s.database_url_override = database_url
        parsed = urlparse(database_url)

        if parsed.username:
            s.db_user = parsed.username
        if parsed.password:
            s.db_password = parsed.password
        if parsed.hostname:
            s.db_host = parsed.hostname
        if parsed.port:
            s.db_port = int(parsed.port)
        if parsed.path and parsed.path != "/":
            s.db_name = parsed.path.lstrip("/")
    else:
        s.db_name = os.getenv("DB_NAME", s.db_name)
        s.db_user = _require_env("DB_USER")
        s.db_password = _require_env("PGPASSWORD")
        s.db_host = os.getenv("DB_HOST", s.db_host)
        s.db_port = int(os.getenv("DB_PORT", s.db_port))
    s.openai_api_key = _require_env("OPENAI_API_KEY")
    s.embed_model = os.getenv("EMBED_MODEL", s.embed_model)
    s.chat_model = os.getenv("CHAT_MODEL", s.chat_model)
    return s
