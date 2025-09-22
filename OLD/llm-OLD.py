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
def embed_text(text: str) -> Optional[List[float]]:
    return _cached_embed(settings.embed_model, text)


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

    relation_templates = {
        "supersedes": "vervangt {refs}",
        "superseded_by": "vervangen door {refs}",
        "supports": "ondersteunt {refs}",
        "contradicts": "spreekt tegen {refs}",
        "related": "gerelateerd aan {refs}",
        "duplicates": "duplicaat van {refs}",
    }
    relation_labels = {
        "supports": "ondersteunt een andere bron",
        "contradicts": "spreekt andere bron(nen) tegen",
        "related": "is contextueel gerelateerd",
        "duplicates": "is een duplicaat van een andere bron",
    }

    def format_doc(idx: int, match: Dict[str, Any]) -> str:
        metadata = match.get("metadata", {})
        relations = {
            key: map_ids_to_refs(metadata.get(key, "")) for key in relation_templates
        }

        status_value = str(metadata.get("status", "")).lower()
        status = "ACTUEEL"
        if relations["superseded_by"] or status_value == "archived":
            status = "VERVANGEN"
        elif status_value == "draft":
            status = "CONCEPT"

        annotations: list[str] = [status]

        relation_to_query = (match.get("relation") or "").strip()
        if relation_to_query:
            annotations.append(
                f"toegevoegd via {relation_labels.get(relation_to_query, relation_to_query)}"
            )

        for key, template in relation_templates.items():
            refs = relations.get(key) or []
            if not refs:
                continue
            if key == "superseded_by":
                # status already maakt duidelijk dat document verouderd is; benoem vervanging expliciet
                annotations.append(template.format(refs=", ".join(refs)))
            elif key == "supersedes":
                annotations.append(template.format(refs=", ".join(refs)))
            else:
                annotations.append(template.format(refs=", ".join(refs)))

        score = match.get("score")
        score_str = (
            f"Relevantie: {score:.2f}\n"
            if isinstance(score, (int, float)) and score > 0
            else ""
        )

        annotation_str = (
            f" ({'; '.join(annotation.strip() for annotation in annotations if annotation)})"
            if annotations
            else ""
        )
        topic = metadata.get("topic", "") or "Onbekend onderwerp"
        tags = metadata.get("tags", "")
        tags_str = f"Tags: {tags}\n" if tags else ""
        summary = metadata.get("summary", "")
        summary_str = f"Samenvatting: {summary}" if summary else ""

        return (
            f"[{idx + 1}] {topic}{annotation_str}\n"
            f"Datum: {metadata.get('date', '')}\n"
            f"{score_str}"
            f"{tags_str}"
            f"{summary_str}"
        ).strip()

    sources_block = "\n\n".join(format_doc(idx, match) for idx, match in enumerate(matches))

    system_prompt = {
        "role": "system",
        "content": (
            "Je bent een kennisbank-assistent voor zorgprofessionals."
            "Je ontvangt een vraag en een set documenten uit PostgreSQL met hun relaties.\n\n"
            "BETEKENIS VAN RELATIES:"
            "- 'ACTUEEL': leidende bron, formeel gepubliceerd."
            "- 'VERVANGEN': vervangen door nieuwere versie; alleen gebruiken als achtergrond."
            "- 'CONCEPT': nog in ontwikkeling; presenteer voorzichtig en markeer als concept."
            "- 'SUPPORT': ondersteunt een andere bron; gebruik voor onderbouwing, niet als enige bewijs."
            "- 'TEGENSTRIJDIG': spreekt een andere bron tegen; benoem het conflict en kies de meest actuele informatie."
            "- 'GERELATEERD': thematisch verwant; optionele context."
            "- 'DUPLICAAT': dubbele inhoud; verwijs liever naar de primaire bron.\n\n"
            "RICHTLIJNEN:"
            "1. Formuleer het kernantwoord uitsluitend op basis van ACTUELE bronnen."
            "2. Voeg alleen context toe uit support/gerelateerde documenten als dit het antwoord versterkt."
            "3. Meld verouderde, conceptuele of tegenstrijdige bronnen expliciet en geef aan wat betrouwbaar is."
            "4. Wanneer geen betrouwbare bron beschikbaar is, geef dit aan en doe een vervolgsuggestie."
            "5. Verwijs naar bronnen alleen met hun nummer [n]."
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


def suggest_entities(text: str, max_items: int = 8) -> List[Dict[str, str]]:
    cleaned = (text or "").strip()
    if not cleaned:
        return []

    try:
        data = _force_json(
            [
                {
                    "role": "system",
                    "content": (
                        "Extraheer relevante entiteiten voor een zorgkennisbank."
                        " Geef per entiteit een type (bijv. app/proces/rol),"
                        " de originele waarde en een genormaliseerde vorm."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        'JSON: {"entities": [{"entity_type":"...","value":"...","canonical_value":"..."}]}\n\n'
                        f"Beperk tot maximaal {max_items} entiteiten.\n\n{cleaned}"
                    ),
                },
            ]
        )
        items = data.get("entities", [])
    except Exception as exc:  # pragma: no cover - depends on remote service
        logger.warning("Kon entiteiten niet extraheren: %s", exc)
        return []

    results: List[Dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        value = str(item.get("value", "")).strip()
        if not value:
            continue
        entity_type = str(item.get("entity_type", "onbekend")).strip() or "onbekend"
        canonical_value = str(item.get("canonical_value") or value).strip().lower()
        results.append(
            {
                "entity_type": entity_type,
                "value": value,
                "canonical_value": canonical_value,
            }
        )

    return results


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
