from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Final

from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec


@dataclass(frozen=True)
class Settings:
    """Immutable application configuration."""

    openai_api_key: str
    pinecone_api_key: str
    index_name: str = "knowledge-base"
    embed_dim: int = 1536
    embed_model: str = "text-embedding-3-small"
    chat_model: str = "gpt-4o-mini"
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-west-2"


_REQUIRED_ENV: Final[tuple[str, str]] = ("OPENAI_API_KEY", "PINECONE_API_KEY")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    values = {}
    for key in _REQUIRED_ENV:
        value = os.getenv(key)
        if not value:
            raise RuntimeError(f"{key} niet gezet")
        values[key] = value

    return Settings(
        openai_api_key=values["OPENAI_API_KEY"],
        pinecone_api_key=values["PINECONE_API_KEY"],
    )


@lru_cache(maxsize=1)
def get_openai_client() -> OpenAI:
    settings = get_settings()
    return OpenAI(api_key=settings.openai_api_key)


@lru_cache(maxsize=1)
def get_pinecone_client() -> Pinecone:
    settings = get_settings()
    return Pinecone(api_key=settings.pinecone_api_key)


@lru_cache(maxsize=1)
def get_vector_index():
    settings = get_settings()
    client = get_pinecone_client()

    if settings.index_name not in client.list_indexes().names():
        client.create_index(
            name=settings.index_name,
            dimension=settings.embed_dim,
            metric="cosine",
            spec=ServerlessSpec(cloud=settings.pinecone_cloud, region=settings.pinecone_region),
        )

    return client.Index(settings.index_name)