from __future__ import annotations

import streamlit as st

from services.knowledge import KnowledgeService

STATE_KEYS = {
    "related_ids": [],
    "supersedes_ids": [],
    "suggestions": [],
}


def render(service: KnowledgeService) -> None:
    st.subheader("Nieuwe kennis toevoegen")
    _ensure_state()

    text = st.text_area("Inhoud")
    topic = st.text_input("Onderwerp")
    created_by = st.text_input("Aangemaakt door")

    if st.button("Zoek mogelijke matches", key="opslaan_suggesties"):
        st.session_state["suggestions"] = service.suggest_relations(text)
        st.session_state["related_ids"] = []
        st.session_state["supersedes_ids"] = []
        _clear_relation_widget_state()

    _render_suggestions()

    if st.button("Opslaan", key="opslaan_entry"):
        if not text.strip():
            st.error("Voer tekst in.")
            return

        result = service.save_entry(
            text=text,
            topic=topic,
            created_by=created_by,
            related_ids=st.session_state["related_ids"],
            supersedes_ids=st.session_state["supersedes_ids"],
        )

        if result.entry_id:
            st.success(f"✅ Opgeslagen met ID: {result.entry_id}")
            if result.summary:
                st.caption(f"Samenvatting: {result.summary}")
            if result.tags:
                st.caption(f"Tags: {', '.join(result.tags)}")
            _reset_state()
        else:
            st.error("Opslaan mislukt. Controleer de logs voor details.")


def _render_suggestions() -> None:
    suggestions = st.session_state["suggestions"]
    if not suggestions:
        return

    st.markdown("#### 💡 Mogelijke matches")
    st.caption("Gerelateerd = inhoudelijk verwant • Supersedes = vervangt dit item")

    related_selected = set(st.session_state.get("related_ids", []))
    supersedes_selected = set(st.session_state.get("supersedes_ids", []))

    for suggestion in suggestions:
        metadata = suggestion.get("metadata", {}) or {}
        raw_id = suggestion.get("id")
        suggestion_id = str(raw_id) if raw_id is not None else None
        if not suggestion_id:
            continue

        score = suggestion.get("score") or 0.0
        header = f"ID={suggestion_id} | Topic={metadata.get('topic', '')} | Score={score:.2f}"

        with st.expander(header):
            st.write("**Samenvatting:**", metadata.get("summary", ""))
            st.write("**Datum:**", metadata.get("date", ""))
            st.write("**Tags:**", metadata.get("tags", ""))
            st.info(metadata.get("text", ""))

            rel_key = f"rel_{suggestion_id}"
            sup_key = f"sup_{suggestion_id}"

            rel_checked = st.checkbox("✅ Gerelateerd", key=rel_key)
            sup_checked = st.checkbox("⚠️ Supersedes", key=sup_key)

            if rel_checked:
                related_selected.add(suggestion_id)
            else:
                related_selected.discard(suggestion_id)

            if sup_checked:
                supersedes_selected.add(suggestion_id)
            else:
                supersedes_selected.discard(suggestion_id)

    st.session_state["related_ids"] = sorted(related_selected)
    st.session_state["supersedes_ids"] = sorted(supersedes_selected)


def _ensure_state() -> None:
    for key, default in STATE_KEYS.items():
        if key not in st.session_state:
            st.session_state[key] = list(default)


def _reset_state() -> None:
    for key in STATE_KEYS:
        st.session_state[key] = []
    _clear_relation_widget_state()


def _clear_relation_widget_state() -> None:
    relation_keys = [key for key in st.session_state.keys() if key.startswith("rel_") or key.startswith("sup_")]
    for key in relation_keys:
        del st.session_state[key]
