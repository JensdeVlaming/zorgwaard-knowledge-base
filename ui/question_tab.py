from __future__ import annotations

from typing import Optional

import streamlit as st

from services.knowledge import Answer, KnowledgeService, Match


def render(service: KnowledgeService) -> None:
    st.subheader("Vraag stellen")
    question = st.text_input(
        "Wat wil je weten?",
        placeholder="Bijvoorbeeld: Hoe maak ik een Knox-account aan?",
    )

    if st.button("Zoeken", key="vraag_zoeken"):
        _handle_search(service, question)


def _handle_search(service: KnowledgeService, question: str) -> None:
    if not question.strip():
        st.warning("Voer eerst een vraag in.")
        return

    matches, answer = service.search(question)
    if not matches:
        st.info("Geen relevante documenten gevonden.")
        return

    col1, col2 = st.columns([2, 1])

    with col1:
        _render_answer(answer)

    with col2:
        _render_sources(matches)


def _render_answer(answer: Optional[Answer]) -> None:
    st.markdown("#### Antwoord")
    if not answer:
        st.info("Geen antwoord beschikbaar.")
        return
    st.info(answer.get("answer", ""))
    with st.expander("Denkspoor"):
        st.json(answer.get("trace", {}))


def _render_sources(matches: list[Match]) -> None:
    st.markdown("#### Bronnen")
    for idx, match in enumerate(matches):
        metadata = match.get("metadata", {}) or {}
        relation = match.get("relation")
        relation_prefix = f"({relation}) " if relation else ""
        header = f"[{idx + 1}] {relation_prefix}{metadata.get('topic', '')} – {metadata.get('date', '')}"
        with st.expander(header):
            st.write("**Samenvatting:**")
            st.write(metadata.get("summary", ""))
            st.write("**Tags:**")
            st.caption(metadata.get("tags", ""))
            st.write("**Tekst:**")
            st.caption(metadata.get("text", ""))
            st.write("**Door:**", metadata.get("created_by", ""))
