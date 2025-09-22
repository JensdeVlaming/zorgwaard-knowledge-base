from __future__ import annotations

import streamlit as st

from infrastructure.llm import entities
from infrastructure.llm.llm_utils import embed_text
from services.note_service import create_note
from services.relation_service import (
    create_relation_entry,
    suggest_relations_for_embedding,
)
from services.summary_service import summarize

DEFAULT_RELATION_LABEL = "Geen relatie"

RELATION_TYPE_MAP = {
    "Ondersteunt": "supports",
    "Spreekt tegen": "contradicts",
    "Vervangt": "supersedes",
    "Gerelateerd": "related",
    "Duplicaat": "duplicate",
}

RELATION_TYPE_OPTIONS = [
    DEFAULT_RELATION_LABEL,
    *RELATION_TYPE_MAP.keys(),
]


def render():
    formContainer, suggestionsContainer = st.columns([5, 3])

    with formContainer:
        st.markdown("### Nieuwe notitie")

        titleContainer, authorContainer = st.columns([3, 1])
        title = titleContainer.text_input("Titel", key="create-note-title")
        author = authorContainer.text_input("Auteur", key="create-note-author")
        content = st.text_area("Inhoud", height=200, key="create-note-content")
        status_display = st.selectbox(
            "Status",
            ["Gepubliceerd", "Concept", "Archief"],
            key="create-note-status",
        )
        status_map = {
            "Gepubliceerd": "published",
            "Concept": "draft",
            "Archief": "archived",
        }
        status = status_map[status_display]

    content_embedding = None
    relation_suggestions = []

    if content.strip():
        relation_suggestions = _get_relation_suggestions(content)

    with suggestionsContainer:
        st.markdown("### Relaties")

        if not content.strip():
            st.caption("Schrijf eerst inhoud om relaties te zien.")
        elif not relation_suggestions:
            st.info("Geen relatie-suggesties gevonden.")
        else:
            _sync_relation_choice_state(relation_suggestions)

            for suggestion in relation_suggestions:
                choice_key = f"relation-choice-{suggestion.note_id}"
                with st.expander(
                    f"{suggestion.title} • {suggestion.score:.2f}", expanded=False
                ):
                    st.caption(suggestion.summary or "Geen samenvatting beschikbaar.")
                    st.selectbox(
                        "Relatie",
                        RELATION_TYPE_OPTIONS,
                        key=choice_key,
                    )
                    st.markdown(
                        """
                        <div style='line-height:1.2; font-size:0.9em; color:gray; margin-bottom:10px;'>
                        <b>Ondersteunt</b> – bevestigt of versterkt andere notitie (bv. handleiding bevestigt procedure)<br>
                        <b>Spreekt tegen</b> – inhoud is tegenstrijdig (bv. A zegt RAM IT, B zegt Zorgwaard)<br>
                        <b>Vervangt</b> – nieuwe versie vervangt de oude (bv. Knox v3 vervangt Knox v2)<br>
                        <b>Gerelateerd</b> – zelfde thema, geen bewijs (bv. Knox-account vs MFA-procedure)<br>
                        <b>Duplicaat</b> – inhoud (bijna) hetzelfde
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

    if st.button("Opslaan", type="primary"):
        if not title.strip() or not content.strip() or not author.strip():
            st.warning("Titel, inhoud en auteur zijn verplicht.")
            return

        summary = summarize(content)
        ent_suggestions = entities.suggest_entities(content)
        embedding_for_note = content_embedding or embed_text(content)

        note = create_note(
            title=title,
            content=content,
            summary=summary,
            author=author,
            status=status,
            embedding=embedding_for_note,
            entities=ent_suggestions,
            tags=[],
        )

        created_relations = []
        if relation_suggestions:
            for suggestion in relation_suggestions:
                choice_key = f"relation-choice-{suggestion.note_id}"
                relation_type = st.session_state.get(
                    choice_key, DEFAULT_RELATION_LABEL
                )
                relation_value = RELATION_TYPE_MAP.get(relation_type)
                if not relation_value:
                    continue

                relation = create_relation_entry(
                    source_note_id=str(note.id),
                    target_note_id=suggestion.note_id,
                    relation_type=relation_value,
                )
                created_relations.append(relation)

        st.success(f"✅ Notitie opgeslagen: {note.title}")
        st.json({"summary": summary, "entities": ent_suggestions})

        if created_relations:
            st.success(
                f"{len(created_relations)} relatie(s) toegevoegd voor deze concept-notitie."
            )

        _reset_form_state()


def _get_content_embedding(content: str | None):
    if not content:
        return None

    cache = st.session_state.setdefault("create-note-embedding-cache", {})
    if cache.get("content") == content:
        return cache.get("embedding")

    embedding = embed_text(content)
    cache["content"] = content
    cache["embedding"] = embedding
    return embedding


def _get_relation_suggestions(content: str, limit: int = 10):
    cache = st.session_state.setdefault("create-note-suggestion-cache", {})
    if cache.get("content") == content:
        return cache.get("suggestions", [])

    embedding = _get_content_embedding(content)
    if not embedding:
        return []
    suggestions = suggest_relations_for_embedding(embedding, limit=limit)

    cache["content"] = content
    cache["suggestions"] = suggestions
    return suggestions


def _sync_relation_choice_state(suggestions):
    tracked_keys = set(st.session_state.get("create-note-relation-keys", []))
    current_keys = {f"relation-choice-{s.note_id}" for s in suggestions}

    for stale_key in tracked_keys - current_keys:
        st.session_state.pop(stale_key, None)

    for key in current_keys:
        st.session_state.setdefault(key, DEFAULT_RELATION_LABEL)

    st.session_state["create-note-relation-keys"] = list(current_keys)


def _reset_form_state():
    for key in [
        "create-note-title",
        "create-note-author",
        "create-note-content",
        "create-note-status",
    ]:
        if key in st.session_state:
            st.session_state[key] = "" if key != "create-note-status" else "Concept"

    for cache_key in [
        "create-note-embedding-cache",
        "create-note-suggestion-cache",
        "create-note-relation-keys",
    ]:
        st.session_state.pop(cache_key, None)

    for key in list(st.session_state.keys()):
        if isinstance(key, str) and key.startswith("relation-choice-"):
            st.session_state.pop(key, None)
