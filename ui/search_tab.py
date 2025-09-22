from __future__ import annotations

import streamlit as st

from infrastructure.llm.answering import answer_from_context
from services.entity_service import list_entities
from services.note_service import search_question_matches


def _load_entity_data() -> dict[str, list[str]]:
    entities = list_entities(limit=200)

    grouped: dict[str, set[str]] = {}
    for entity in entities:
        type_label = str(entity.entity_type or "Onbekend")
        value_label = str(entity.canonical_value or entity.value or "Onbekend")
        grouped.setdefault(type_label, set()).add(value_label)

    return {type_label: sorted(values) for type_label, values in grouped.items()}


def render():
    entity_data = _load_entity_data()

    questionContainer, filterContainer = st.columns([4, 2])
    with questionContainer:
        question = st.text_input(
            "Wat wil je weten?",
            placeholder="Bijv: Hoe maak ik een Knox-account aan?",
        )
        search_clicked = st.button("Zoek", type="primary")

    with filterContainer:
        selected_type = None
        selected_values: list[str] = []
        if entity_data:
            type_options = sorted(entity_data.keys())
            chosen_type = st.selectbox(
                "Entiteitstype",
                options=["Alle", *type_options],
            )

            if chosen_type != "Alle":
                value_options = entity_data.get(chosen_type, [])
                selected_values = st.multiselect(
                    "Waarden",
                    options=value_options,
                    format_func=lambda value: f"{value} [{chosen_type}]",
                    key=f"entity-values-{chosen_type}",
                )
                selected_type = chosen_type
            else:
                selected_values = []
                selected_type = None

            st.caption(
                "Filter optioneel op een entiteitstype en bijbehorende waarde(s). Laat leeg voor alle notities."
            )
        else:
            st.caption("Nog geen entiteiten beschikbaar.")

    if search_clicked:
        question_clean = question.strip()
        if not question_clean:
            st.warning("Vul een vraag in om te zoeken.")
            return

        try:
            matches, _ = search_question_matches(
                question_clean,
                limit=5,
                entity_type=selected_type,
                entity_values=selected_values,
            )
        except ValueError as exc:
            st.warning(str(exc))
            return
        except RuntimeError as exc:
            st.error(str(exc))
            return

        if not matches:
            st.info("Geen notities gevonden die bij deze vraag passen.")
            return

        out = answer_from_context(question_clean, matches)
        answerContainer, sourcesContainer = st.columns([4, 2])

        with answerContainer:
            st.info(out["answer"])
            with st.expander("Trace"):
                st.json(out["trace"])

        with sourcesContainer:
            st.subheader("Bronnen")
            sources = out["trace"].get("matches", [])
            if not sources:
                st.info("Geen bronnen gevonden.")
            else:
                for idx, src in enumerate(sources, start=1):
                    with st.expander(f"[{idx}] - {src['metadata']['topic']}"):
                        if src["metadata"].get("summary"):
                            st.caption(src["metadata"]["summary"])
                        st.markdown(f"*Status: {src['metadata'].get('status', 'Onbekend')}*")
                        st.markdown(f"- Score: {src['score']:.2f}")
                        st.markdown(f"- ID: {src['id']}")
