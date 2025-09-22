from __future__ import annotations

from typing import Dict, List

import streamlit as st

from infrastructure.db import EntityRecord
from services.knowledge import EnrichmentResult, KnowledgeService, SaveNoteResult


def render(service: KnowledgeService) -> None:
    _init_state(service)

    status_options = list(service.status_options().keys())
    relation_types = service.relation_types()
    entities = service.list_entities()
    entity_options = {record.id: f"{record.label} ({record.entity_type})" for record in entities}

    form_col, relation_col = st.columns([3, 2], vertical_alignment="top")

    with form_col:
        st.markdown("### Nieuwe notitie")
        title = st.text_input(
            "Titel",
            key="note_title",
            placeholder="Bijvoorbeeld: Retour telefoons instructies",
        )
        author = st.text_input("Auteur", key="note_author")
        status_label = st.selectbox("Status", status_options, key="note_status_display")
        content = st.text_area("Inhoud", key="note_content", height=320)

        preview_placeholder = st.container()

    with relation_col:
        _render_relation_sidebar(service, relation_types, content)

    st.divider()

    col_enrich, col_save = st.columns([1, 1])
    with col_enrich:
        if st.button("LLM verrijking", key="note_enrich_button"):
            enrichment = _handle_enrichment_action(service, content, refresh_relations=True)
            if enrichment:
                st.success("LLM verrijking toegepast.")

    with col_save:
        if st.button("Opslaan notitie", type="primary", key="note_save_button"):
            cleaned_content = content.strip()
            if not cleaned_content:
                st.warning("Voer eerst inhoud in voordat je opslaat.")
            else:
                try:
                    with st.spinner("Notitie verrijken en opslaan..."):
                        enrichment = _handle_enrichment_action(
                            service, content, refresh_relations=True
                        )
                        if enrichment is None:
                            raise RuntimeError("Geen LLM verrijking beschikbaar.")
                        entity_records = ensure_unique_entities(enrichment.entities)
                        result = service.save_note(
                            title=title,
                            content=content,
                            author=author,
                            status_label=status_label,
                            tags=enrichment.tags,
                            relations=st.session_state["note_relations"],
                            entity_ids=[record.id for record in entity_records],
                        )
                    _handle_save_success(result)
                except Exception as exc:
                    st.error(f"Opslaan mislukt: {exc}")

    with preview_placeholder:
        _render_enrichment_preview(entity_options)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_state(service: KnowledgeService) -> None:
    state = st.session_state
    if "note_title" not in state:
        state["note_title"] = ""
    if "note_status_display" not in state:
        state["note_status_display"] = "Published"
    if "note_content" not in state:
        state["note_content"] = ""
    if "note_entity_ids" not in state:
        state["note_entity_ids"] = []
    if "note_entities_detail" not in state:
        state["note_entities_detail"] = []
    if "note_tags" not in state:
        state["note_tags"] = []
    if "note_relations" not in state:
        state["note_relations"] = []
    if "note_relation_suggestions" not in state:
        state["note_relation_suggestions"] = []
    if "note_relation_suggestions_source" not in state:
        state["note_relation_suggestions_source"] = ""
    if "note_show_manual_relation" not in state:
        state["note_show_manual_relation"] = False
    if "note_preview" not in state:
        state["note_preview"] = None
    if "note_enriched_summary" not in state:
        state["note_enriched_summary"] = None


def _render_enrichment_preview(entity_options: Dict[str, str]) -> None:
    summary = st.session_state.get("note_enriched_summary")
    tags = st.session_state.get("note_tags", [])
    entity_details = st.session_state.get("note_entities_detail", [])

    if not any([summary, tags, entity_details]):
        st.caption("Tags, entiteiten en samenvatting worden automatisch aangevuld bij het opslaan.")
        return

    with st.container(border=True):
        st.caption("LLM suggesties")
        if summary:
            st.markdown(f"**Samenvatting**\n\n{summary}")
        if tags:
            tag_html = " ".join(
                [
                    f"<span style='background-color:#eef5ff; color:#1f3b57; padding:2px 8px; "
                    f"border-radius:12px; margin-right:5px; font-size:0.85em;'>#{tag}</span>"
                    for tag in tags
                ]
            )
            st.markdown(tag_html, unsafe_allow_html=True)
        if entity_details or st.session_state.get("note_entity_ids"):
            st.markdown("**Entiteiten**")
            if entity_details:
                for entity in entity_details:
                    st.markdown(f"- {entity['label']} ({entity['entity_type']})")
            else:
                for entity_id in st.session_state.get("note_entity_ids", []):
                    label = entity_options.get(entity_id)
                    if label:
                        st.markdown(f"- {label}")


def _render_relation_sidebar(service: KnowledgeService, relation_types: List[str], content: str) -> None:
    st.markdown("### Relaties")

    _refresh_relation_suggestions(service, content, force=False)

    action_col_left, action_col_right = st.columns([1, 1])

    with action_col_left:
        if st.button("Vernieuw suggesties", key="note_relation_refresh_button"):
            if not content.strip():
                st.warning("Voer eerst inhoud in voor suggesties.")
            else:
                _refresh_relation_suggestions(service, content, force=True)

    with action_col_right:
        manual_open = st.session_state.get("note_show_manual_relation", False)
        if not manual_open:
            if st.button("Handmatige relatie toevoegen", key="note_relation_manual_open"):
                st.session_state["note_show_manual_relation"] = True
                st.rerun()
        else:
            if st.button("Sluit handmatige relatie", key="note_relation_manual_close_button"):
                st.session_state["note_show_manual_relation"] = False
                st.rerun()

    suggestions = st.session_state.get("note_relation_suggestions", [])
    if suggestions:
        st.caption("Suggesties op basis van de huidige inhoud")
        _render_relation_suggestions(relation_types, suggestions)
    else:
        st.caption(
            "Nog geen relatiesuggesties beschikbaar. Voeg inhoud toe en klik op 'Vernieuw suggesties'."
        )

    manual_open = st.session_state.get("note_show_manual_relation", False)
    if manual_open:
        with st.container(border=True):
            st.markdown("**Handmatige relatie**")
            _render_relation_editor(service, relation_types)

    st.divider()
    _render_relation_list()


def _render_relation_suggestions(relation_types: List[str], suggestions: List[Dict[str, object]]) -> None:
    if not suggestions:
        return

    default_index = relation_types.index("related") if "related" in relation_types else 0

    for idx, suggestion in enumerate(suggestions):
        note_id = suggestion.get("id") or f"unknown_{idx}"
        title = suggestion.get("title", "Onbekende notitie")
        status = str(suggestion.get("status", "") or "").title()
        score = suggestion.get("score", 0.0) or 0.0
        summary = suggestion.get("summary")
        tags = suggestion.get("tags") or []

        with st.container(border=True):
            st.markdown(f"**{title}**")
            st.caption(f"Status: {status or 'onbekend'} • Score: {score:.2f}")
            if summary:
                st.caption(summary)
            if tags:
                st.caption("Tags: " + ", ".join(tags))

            select_col, button_col = st.columns([3, 1])
            widget_suffix = f"{note_id}_{idx}"
            selected_type = select_col.selectbox(
                "Relatietype",
                relation_types,
                index=default_index,
                key=f"suggest_relation_type_{widget_suffix}",
                label_visibility="collapsed",
            )
            if button_col.button("Voeg toe", key=f"suggest_add_{widget_suffix}"):
                label = f"{title} ({status})" if status else title
                if _add_relation_entry(selected_type, note_id, label):
                    st.success("Relatie toegevoegd.")
                else:
                    st.info("Deze relatie staat al in de lijst.")


def _render_relation_editor(service: KnowledgeService, relation_types: List[str]) -> None:
    col_type, col_search, col_action = st.columns([1, 2, 1])
    relation_type = col_type.selectbox("Relatietype", relation_types, key="note_relation_type")
    search_term = col_search.text_input("Zoek bestaande notitie", key="note_relation_search")

    options = service.list_note_options(search_term) if search_term else []
    option_labels = {item["id"]: f"{item['title']} ({item['status']})" for item in options}
    placeholder = "Selecteer notitie" if options else "Geen resultaten"
    selected_label = col_search.selectbox(
        "Doelnotitie",
        options=[placeholder] + list(option_labels.values()),
        key="note_relation_target",
    )

    if col_action.button("Relatie toevoegen", key="note_relation_add"):
        if selected_label == placeholder:
            st.warning("Selecteer een notitie om de relatie toe te voegen.")
            return
        target_id = next(
            (note_id for note_id, label in option_labels.items() if label == selected_label),
            None,
        )
        if not target_id:
            st.warning("Kon de geselecteerde notitie niet bepalen.")
            return
        if _add_relation_entry(relation_type, target_id, selected_label):
            st.success("Relatie toegevoegd.")
        else:
            st.info("Deze relatie staat al in de lijst.")


def _render_relation_list() -> None:
    relations = st.session_state["note_relations"]
    if not relations:
        st.caption("Nog geen relaties toegevoegd.")
        return

    for idx, relation in enumerate(relations):
        rel_col, btn_col = st.columns([5, 1])
        rel_col.markdown(f"- **{relation['relation_type']}** → {relation['target_title']}")
        if btn_col.button("Verwijder", key=f"remove_relation_{idx}"):
            del relations[idx]
            st.rerun()


def _handle_enrichment_action(
    service: KnowledgeService, content: str, *, refresh_relations: bool
) -> EnrichmentResult | None:
    cleaned_content = (content or "").strip()
    if not cleaned_content:
        st.warning("Voer eerst inhoud in voordat je verrijking aanvraagt.")
        return None

    enrichment = service.generate_enrichment(cleaned_content)
    _apply_enrichment(enrichment)

    if refresh_relations:
        _refresh_relation_suggestions(service, cleaned_content, force=True)

    return enrichment


def _refresh_relation_suggestions(
    service: KnowledgeService, content: str, *, force: bool
) -> None:
    cleaned_content = (content or "").strip()
    state = st.session_state
    if not cleaned_content or len(cleaned_content) < 60:
        if force:
            _update_relation_suggestions([], cleaned_content)
        return

    if not force:
        has_existing = bool(state.get("note_relation_suggestions"))
        same_source = state.get("note_relation_suggestions_source") == cleaned_content
        if has_existing and same_source:
            return

    try:
        suggestions = service.suggest_relations(cleaned_content)
    except Exception as exc:  # pragma: no cover - Streamlit context
        st.warning(f"Kon relatiesuggesties niet ophalen: {exc}")
        return

    _update_relation_suggestions(suggestions, cleaned_content)


def _update_relation_suggestions(suggestions: List[object], source_text: str) -> None:
    serialised: List[Dict[str, object]] = []
    for match in suggestions or []:
        note = getattr(match, "note", None)
        if not note:
            continue
        serialised.append(
            {
                "id": getattr(note, "id", ""),
                "title": getattr(note, "title", ""),
                "status": getattr(note, "status", ""),
                "summary": getattr(note, "summary", ""),
                "tags": getattr(note, "tags", []),
                "score": getattr(match, "score", 0.0),
            }
        )
    state = st.session_state
    state["note_relation_suggestions"] = serialised
    state["note_relation_suggestions_source"] = source_text


def _add_relation_entry(relation_type: str, target_id: str, target_title: str) -> bool:
    if not relation_type or not target_id:
        return False

    relation_entry = {
        "relation_type": relation_type,
        "target_id": target_id,
        "target_title": target_title,
    }
    relations = st.session_state["note_relations"]
    if relation_entry in relations:
        return False
    relations.append(relation_entry)
    return True


def _apply_enrichment(enrichment: EnrichmentResult) -> None:
    state = st.session_state
    state["note_enriched_summary"] = enrichment.summary
    state["note_tags"] = enrichment.tags or []

    entity_records = ensure_unique_entities(enrichment.entities)
    state["note_entity_ids"] = [record.id for record in entity_records]
    state["note_entities_detail"] = [
        {"id": record.id, "label": record.label, "entity_type": record.entity_type}
        for record in entity_records
    ]


def ensure_unique_entities(entities: List[EntityRecord]) -> List[EntityRecord]:
    unique: Dict[str, EntityRecord] = {}
    for entity in entities:
        unique[entity.id] = entity
    return list(unique.values())


def _handle_save_success(result: SaveNoteResult) -> None:
    st.success(f"Notitie opgeslagen (ID: {result.detail.note.id})")
    st.session_state["note_preview"] = result.detail
