from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

import numpy as np
import streamlit as st

from core.config import get_openai_client, get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


# ------------------------------------------------------------------
# Low-level helpers
# ------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _cached_embed(model: str, text: str) -> Optional[List[float]]:
    text = (text or "").strip()
    if not text:
        return None

    try:
        client = get_openai_client()
        response = client.embeddings.create(input=text, model=model)
        return response.data[0].embedding
    except Exception as exc:  # pragma: no cover - depends on remote service
        logger.exception("Embedding fout", exc_info=exc)
        st.error(f"Embedding fout: {exc}")
        return None


def embed_text(text: str) -> Optional[List[float]]:
    return _cached_embed(settings.embed_model, text)


def llm_chat(messages: List[Dict[str, str]], model: Optional[str] = None) -> str:
    try:
        client = get_openai_client()
        response = client.chat.completions.create(model=model or settings.chat_model, messages=messages)
        return response.choices[0].message.content
    except Exception as exc:  # pragma: no cover - depends on remote service
        logger.exception("LLM fout", exc_info=exc)
        st.error(f"LLM fout: {exc}")
        return ""


# ------------------------------------------------------------------
# Retrieval-augmented answering
# ------------------------------------------------------------------
def answer_from_context(question: str, matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    id_to_num = {match.get("id"): str(index + 1) for index, match in enumerate(matches)}

    def map_ids_to_refs(raw: str) -> List[str]:
        if not raw:
            return []
        return [f"[{id_to_num.get(identifier.strip(), '?')}]" for identifier in raw.split(",") if identifier.strip()]

    def format_doc(idx: int, match: Dict[str, Any]) -> str:
        metadata = match.get("metadata", {})
        supersedes = map_ids_to_refs(metadata.get("supersedes", ""))
        superseded_by = map_ids_to_refs(metadata.get("superseded_by", ""))

        status = "ACTUEEL"
        notes: list[str] = []
        if supersedes:
            notes.append(f"vervangt {', '.join(supersedes)}")
        if superseded_by:
            status = "VEROUDERD"
            notes.append(f"vervangen door {', '.join(superseded_by)}")

        notes_str = f" ({status}{', ' + ', '.join(notes) if notes else ''})"

        return (
            f"[{idx + 1}]{notes_str}\n"
            f"Topic: {metadata.get('topic', '')}\n"
            f"Date: {metadata.get('date', '')}\n"
            f"Tags: {metadata.get('tags', '')}\n"
            f"Summary: {metadata.get('summary', '')}"
        )

    sources_block = "\n\n".join(format_doc(idx, match) for idx, match in enumerate(matches))

    system_prompt = {
        "role": "system",
        "content": (
            "Je bent een kennisbank-assistent.\n\n"
            "DOCUMENTRELATIES:\n"
            "- 'ACTUEEL': dit document vervangt oudere documenten en is de enige geldige hoofdbron.\n"
            "- 'VEROUDERD': dit document is vervangen door een nieuwer document. Gebruik deze alleen ter context, maar niet als hoofdbron.\n"
            "- 'related_to': inhoudelijk verwant, nooit leidend.\n\n"
            "REGELS VOOR ANTWOORDEN:\n"
            "1. Baseer je antwoord uitsluitend op de ACTUELE documenten.\n"
            "2. Voeg extra uitleg uit VEROUDERDE of RELATED documenten toe als context.\n"
            "3. Verwijs naar bronnen alleen met hun nummer [n]."
        ),
    }

    user_prompt = {
        "role": "user",
        "content": f"Vraag: {question}\n\nBronnen:\n{sources_block}",
    }

    answer = llm_chat([system_prompt, user_prompt])

    return {
        "answer": answer,
        "trace": {
            "question": question,
            "system": system_prompt,
            "prompt": user_prompt["content"],
            "matches": matches,
        },
    }


# ------------------------------------------------------------------
# Summarisation & Tagging
# ------------------------------------------------------------------
CONTROLLED_TAGS: List[str] = []


def summarize_and_tag(text: str, top_k: int = 6) -> Dict[str, Any]:
    summary = _summarize_chunks(text)
    llm_candidates = _llm_tag_candidates(text, k=20)
    statistical_candidates = _stat_tag_candidates(text, top_n=20)

    candidates = list(dict.fromkeys(_normalize_tag(candidate) for candidate in (llm_candidates + statistical_candidates)))
    candidates = [candidate for candidate in candidates if 3 <= len(candidate) <= 40]

    doc_embedding = embed_text(text) or embed_text(summary) or [0.0] * settings.embed_dim
    if not candidates:
        return {"summary": summary, "tags": []}

    candidate_embeddings = [np.array(embed_text(candidate) or np.zeros(settings.embed_dim)) for candidate in candidates]
    selected_indexes = _mmr(np.array(doc_embedding), candidate_embeddings, lambda_=0.7, k=top_k)
    tags = [_nearest_in_taxonomy(candidates[idx]) for idx in selected_indexes]

    return {
        "summary": summary,
        "tags": list(dict.fromkeys([tag for tag in tags if tag])),
    }


# --- Internal helpers -------------------------------------------------
def _force_json(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    try:
        client = get_openai_client()
        response = client.chat.completions.create(
            model=settings.chat_model,
            messages=messages,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)
    except Exception as exc:  # pragma: no cover - depends on remote service
        logger.exception("LLM json parse fout", exc_info=exc)
        raise


def _split_chunks(text: str, max_chars: int = 6000) -> List[str]:
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]
    if not paragraphs:
        return [text[:max_chars]] if text else []

    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 2 <= max_chars:
            current = f"{current}\n\n{paragraph}" if current else paragraph
        else:
            if current:
                chunks.append(current)
            current = paragraph
    if current:
        chunks.append(current)

    return chunks


def _summarize_chunks(text: str) -> str:
    chunks = _split_chunks(text)
    partials: list[str] = []

    for chunk in chunks:
        try:
            data = _force_json([
                {"role": "system", "content": "Vat bondig samen (zorgcontext)."},
                {"role": "user", "content": "JSON: {\"summary\":\"...\"}\n\n" + chunk},
            ])
            partials.append(data.get("summary", "").strip())
        except Exception:
            partials.append(chunk[:300])

    synthesis_input = "\n\n".join(f"- {item}" for item in partials if item)
    try:
        data = _force_json([
            {"role": "system", "content": "Combineer bullets tot één samenvatting."},
            {"role": "user", "content": "JSON: {\"summary\":\"...\"}\n\n" + synthesis_input},
        ])
        return data.get("summary", "").strip()
    except Exception:
        return synthesis_input[:300]


def _llm_tag_candidates(text: str, k: int = 20) -> List[str]:
    try:
        data = _force_json([
            {"role": "system", "content": "Extraheer trefwoorden voor zorg-kennisbank."},
            {
                "role": "user",
                "content": f"Genereer {k} kandidaten. JSON: {{\"candidates\": [\"...\"]}}\n\n{text}",
            },
        ])
        return [str(candidate).strip().lower() for candidate in data.get("candidates", []) if str(candidate).strip()]
    except Exception:
        return []


_DUTCH_STOP = {
    "de",
    "het",
    "een",
    "en",
    "of",
    "dat",
    "die",
    "voor",
    "met",
    "zonder",
    "op",
    "tot",
    "van",
    "in",
    "uit",
    "bij",
    "aan",
    "als",
    "te",
    "door",
    "per",
    "naar",
    "om",
    "is",
    "zijn",
    "wordt",
    "worden",
    "kan",
    "kunnen",
    "moet",
    "moeten",
    "mag",
    "mogen",
    "niet",
    "wel",
}

_EN_STOP = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "for",
    "to",
    "of",
    "in",
    "on",
    "at",
    "by",
    "from",
    "with",
    "without",
    "is",
    "are",
    "be",
    "been",
    "being",
    "this",
    "that",
    "these",
    "those",
    "as",
    "it",
    "its",
    "into",
    "over",
}


def _stat_tag_candidates(text: str, top_n: int = 20) -> List[str]:
    tokens = [token.lower() for token in re.findall(r"[a-zA-ZÀ-ÿ0-9\-]+", text)]
    filtered = [token for token in tokens if token not in _DUTCH_STOP and token not in _EN_STOP and len(token) > 2]

    frequency: dict[str, float] = {}
    for token in filtered:
        frequency[token] = frequency.get(token, 0) + 1

    for index in range(len(filtered) - 1):
        bigram = f"{filtered[index]} {filtered[index + 1]}"
        frequency[bigram] = frequency.get(bigram, 0) + 1.5

    for index in range(len(filtered) - 2):
        trigram = f"{filtered[index]} {filtered[index + 1]} {filtered[index + 2]}"
        frequency[trigram] = frequency.get(trigram, 0) + 2.0

    ranked = sorted(frequency.items(), key=lambda item: item[1], reverse=True)
    return [word for word, _ in ranked[: top_n * 2]]


def _cos_sim(a: np.ndarray, b: np.ndarray) -> float:
    norm_a, norm_b = np.linalg.norm(a), np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _mmr(document_embedding: np.ndarray, candidate_embeddings: List[np.ndarray], lambda_: float = 0.7, k: int = 6) -> List[int]:
    chosen: list[int] = []
    candidates = list(range(len(candidate_embeddings)))
    relevance = [_cos_sim(document_embedding, embedding) for embedding in candidate_embeddings]

    while candidates and len(chosen) < k:
        if not chosen:
            index = int(np.argmax(relevance))
            chosen.append(index)
            candidates.remove(index)
            continue

        scores: list[tuple[int, float]] = []
        for candidate_index in candidates:
            diversity = max((_cos_sim(candidate_embeddings[candidate_index], candidate_embeddings[chosen_idx]) for chosen_idx in chosen), default=0.0)
            score = lambda_ * relevance[candidate_index] - (1 - lambda_) * diversity
            scores.append((candidate_index, score))

        best = max(scores, key=lambda item: item[1])[0]
        chosen.append(best)
        candidates.remove(best)

    return chosen


def _normalize_tag(tag: str) -> str:
    tag = tag.lower().strip()
    tag = re.sub(r"\s+", " ", tag)
    tag = re.sub(r"[^\w\s\-]", "", tag)
    return tag


def _nearest_in_taxonomy(tag: str) -> str:
    if not CONTROLLED_TAGS:
        return tag

    base = [(_normalize_tag(candidate), candidate) for candidate in CONTROLLED_TAGS]
    embeddings = [embed_text(normalized) for normalized, _ in base]

    tag_embedding = embed_text(tag)
    if tag_embedding is None:
        return tag

    similarities = [
        _cos_sim(np.array(tag_embedding), np.array(candidate_embedding))
        if candidate_embedding is not None
        else 0.0
        for candidate_embedding in embeddings
    ]

    if similarities and max(similarities) >= 0.80:
        best_index = int(np.argmax(similarities))
        return base[best_index][1]

    return tag