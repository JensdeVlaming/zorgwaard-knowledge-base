from __future__ import annotations

from typing import Dict, List

import streamlit as st

from services.knowledge import ChatResult, KnowledgeService

RELATION_LABELS: Dict[str, str] = {
    "related": "Gerelateerd",
    "supports": "Ondersteunt",
    "contradicts": "Tegenspreekt",
    "supersedes": "Vervangt",
    "duplicates": "Dupliceert",
}


def render(service: KnowledgeService) -> None:
    st.subheader("Stel je vraag")
    entities = service.list_entities()
    entities_by_type: Dict[str, List[str]] = {}
    for record in entities:
        entities_by_type.setdefault(record.entity_type, []).append(record.id)
    type_options = sorted(entities_by_type.keys())

    entity_options = {record.id: f"{record.label} ({record.entity_type})" for record in entities}
    entity_labels = {label: entity_id for entity_id, label in entity_options.items()}

    query_col, filter_col = st.columns([3, 2], vertical_alignment="top")

    question = query_col.text_input(
        "Wat wil je weten?",
        key="chat_question",
        placeholder="Typ hier je vraag...",
    )
    search_clicked = query_col.button("Zoek en beantwoord", type="primary", key="chat_submit")

    with filter_col:
        selected_types = st.multiselect(
            "Filter op type",
            options=type_options,
            help="Optioneel: filter eerst op een entiteitstype.",
        )

        available_entities = [
            label
            for entity_id, label in entity_options.items()
            if not selected_types or any(
                entity_id in entities_by_type[entity_type] for entity_type in selected_types
            )
        ]

        selected_filters = st.multiselect(
            "Filter op entiteiten (optioneel)",
            options=available_entities,
        )

    filter_ids = [entity_labels[label] for label in selected_filters]

    if search_clicked:
        if not question.strip():
            st.warning("Voer eerst een vraag in.")
        else:
            try:
                result = service.chat(question, filter_ids)
            except Exception as exc:
                st.error(f"Zoeken mislukt: {exc}")
            else:
                if not result.matches:
                    st.info("Geen resultaten gevonden.")
                else:
                    _render_answer(result)

def _render_answer(result: ChatResult) -> None:
    answer_col, sources_col = st.columns([3, 2], vertical_alignment="top")

    with answer_col:
        st.markdown("### Antwoord")
        st.markdown(result.answer or "Geen antwoord beschikbaar.")

        with st.expander("Trace LLM", expanded=False):
            if result.trace:
                st.json(result.trace)
            else:
                st.caption("Geen trace beschikbaar.")

    with sources_col:
        st.markdown("### Bronnen")
        title_lookup = {match.note.id: match.note.title for match in result.matches}
        for idx, match in enumerate(result.matches, start=1):
            note = match.note
            relation = match.relation
            date_str = note.created_at.strftime("%d-%m-%Y") if note.created_at else "-"
            header = f"[{idx}] {note.title} • {date_str}"
            with st.expander(header, expanded=False):
                if relation:
                    relation_label = RELATION_LABELS.get(relation, relation)
                    st.caption(f"Relatie: {relation_label}")
                if match.score is not None:
                    st.caption(f"Score: {match.score:.2f}")
                st.markdown(f"**Status:** {note.status}")
                st.markdown(f"**Auteur:** {note.author_id or '-'}")
                tags = note.tags or []
                st.markdown(f"**Tags:** {', '.join(tags) if tags else '-'}")
                if match.relations.get("supersedes"):
                    supersedes_titles = [
                        title_lookup.get(doc_id, doc_id) for doc_id in match.relations["supersedes"]
                    ]
                    st.markdown(f"**Vervangt:** {', '.join(supersedes_titles)}")
                if match.relations.get("superseded_by"):
                    replaced_by_titles = [
                        title_lookup.get(doc_id, doc_id)
                        for doc_id in match.relations["superseded_by"]
                    ]
                    st.markdown(f"**Vervangen door:** {', '.join(replaced_by_titles)}")
                st.markdown("#### Samenvatting")
                st.markdown(note.summary or "-")
                st.markdown("#### Inhoud")
                st.markdown(note.content)
