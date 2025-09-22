from __future__ import annotations

import textwrap

import streamlit as st
from streamlit_agraph import Config, Edge, Node, agraph

from infrastructure.db import NoteDetail
from services.knowledge import KnowledgeService


def render(service: KnowledgeService) -> None:
    st.subheader("Beheer van notities, entiteiten en relaties")

    # Tabs for different management sections
    tab_notes, tab_entities, tab_relations, tab_graph = st.tabs(["Notities", "Entiteiten", "Relaties", "Grafiek"])

    with tab_notes:
        _render_notes_section(service)

    with tab_entities:
        _render_entities_section(service)

    with tab_relations:
        _render_relations_section(service)

    with tab_graph:
        _render_relations_graph_tab(service)

# ---------------------------------------------------------------------------
# Notes Management Section
# ---------------------------------------------------------------------------

def _render_notes_section(service: KnowledgeService) -> None:
    st.markdown("### Alle notities")

    limit = st.number_input(
        "Aantal te tonen", min_value=10, max_value=500, value=50, step=10, key="notes_limit"
    )
    st.button("Vernieuwen", key="refresh_notes")

    try:
        notes = service.list_all_notes(limit=limit)
        if not notes:
            st.info("Geen notities gevonden.")
            return

        search_term = st.text_input("🔍 Zoek in titels", key="notes_search")
        if search_term:
            notes = [n for n in notes if search_term.lower() in n.title.lower()]

        if not notes:
            st.warning("Geen notities gevonden met deze zoekterm.")
            return

        for note in notes:
            detail: NoteDetail = service.load_note(note.id)

            with st.container(border=True):
                col_left, col_right = st.columns([3, 2])

                # --- Linkerzijde: volledige notitie ---
                with col_left:
                    status_icon = {
                        "published": "🟢",
                        "draft": "🟡",
                        "archived": "🔴"
                    }.get(note.status, "⚪")

                    st.markdown(f"### {note.title} {status_icon}")
                    st.caption(
                        f"Auteur: {note.author_id or 'Onbekend'} | "
                        f"Aangemaakt: {note.created_at.strftime('%d-%m-%Y %H:%M')} | "
                        f"Gewijzigd: {note.updated_at.strftime('%d-%m-%Y %H:%M')}"
                    )

                    if note.tags:
                        tag_html = " ".join(
                            [f"<span style='background-color:#e0e0e0; color:#333; padding:2px 8px; "
                            f"border-radius:12px; margin-right:5px; font-size:0.85em;'>#{t}</span>"
                            for t in note.tags]
                        )
                        st.markdown(tag_html, unsafe_allow_html=True)

                    if note.summary:
                        st.markdown("#### Samenvatting")
                        st.markdown(note.summary or "_Geen samenvatting_")

                    st.markdown("#### Inhoud")
                    st.markdown(note.content or "_Geen inhoud_")

                # --- Rechterzijde: relaties + target inhoud ---
                with col_right:
                    if detail.relations:
                        st.markdown("**Relaties**")
                        for relation in detail.relations:
                            try:
                                target_detail: NoteDetail = service.load_note(relation.target_id)
                                target_note = target_detail.note

                                with st.container(border=True):
                                    # compacte card
                                    st.markdown(f"**{target_note.title} ({relation.relation_type})**")
                                    st.caption(f"Status: {relation.target_status}")
                                    if target_note.summary:
                                        st.caption(target_note.summary)

                                    # volledige note in een popover
                                    with st.popover("Bekijk volledige notitie"):
                                        st.markdown(f"### {target_note.title}")
                                        if target_note.summary:
                                            st.markdown(f"**Samenvatting:** {target_note.summary}")
                                        st.markdown("#### Inhoud")
                                        st.markdown(target_note.content or "_Geen inhoud_")

                            except Exception as e:
                                st.error(f"Kon target niet laden: {e}")

    except Exception as exc:
        st.error(f"Fout bij ophalen notities: {exc}")

# ---------------------------------------------------------------------------
# Entities Management Section
# ---------------------------------------------------------------------------

def _render_entities_section(service: KnowledgeService) -> None:
    st.markdown("### Alle entiteiten")

    # Refresh button
    if st.button("Vernieuwen", key="refresh_entities"):
        pass  # Streamlit will re-run automatically

    try:
        entities = service.list_entities()

        if not entities:
            st.info("Geen entiteiten gevonden.")
            return

        st.markdown(f"**Totaal:** {len(entities)} entiteiten")

        # Search/filter
        search_term = st.text_input("Zoek in entiteiten", key="entities_search")
        entity_type_filter = st.selectbox(
            "Filter op type",
            options=["Alle types"] + sorted(list(set(entity.entity_type for entity in entities))),
            key="entities_type_filter"
        )

        # Filter entities
        filtered_entities = entities

        if search_term:
            filtered_entities = [
                entity for entity in filtered_entities
                if search_term.lower() in entity.label.lower()
                or search_term.lower() in (entity.canonical_value or "").lower()
            ]

        if entity_type_filter != "Alle types":
            filtered_entities = [
                entity for entity in filtered_entities
                if entity.entity_type == entity_type_filter
            ]

        if not filtered_entities:
            st.warning("Geen entiteiten gevonden met de huidige filters.")
            return

        st.markdown(f"**Getoond:** {len(filtered_entities)} van {len(entities)} entiteiten")

        # Group by entity type for better organization
        entities_by_type = {}
        for entity in filtered_entities:
            if entity.entity_type not in entities_by_type:
                entities_by_type[entity.entity_type] = []
            entities_by_type[entity.entity_type].append(entity)

        # Display entities grouped by type
        for entity_type in sorted(entities_by_type.keys()):
            with st.expander(f"{entity_type.title()} ({len(entities_by_type[entity_type])})", expanded=True):
                for entity in sorted(entities_by_type[entity_type], key=lambda e: e.label.lower()):
                    col_entity, col_id = st.columns([3, 1])
                    with col_entity:
                        canonical_text = ""
                        if entity.canonical_value and entity.canonical_value != entity.label.lower():
                            canonical_text = f" → `{entity.canonical_value}`"
                        st.markdown(f"**{entity.label}**{canonical_text}")

    except Exception as exc:
        st.error(f"Fout bij ophalen entiteiten: {exc}")


# ---------------------------------------------------------------------------
# Relations Management Section
# ---------------------------------------------------------------------------

def _render_relations_section(service: KnowledgeService) -> None:
    st.markdown("### Alle relaties")

    # Controls
    col_limit, col_refresh = st.columns([3, 1])
    with col_limit:
        limit = st.number_input("Aantal te tonen", min_value=10, max_value=500, value=100, step=10, key="relations_limit")
    with col_refresh:
        st.write("")  # Spacing
        st.button("Vernieuwen", key="refresh_relations")

    try:
        relations = service.list_all_relations(limit=limit)

        if not relations:
            st.info("Geen relaties gevonden.")
            return

        st.markdown(f"**Totaal:** {len(relations)} relaties")

        # Shared helpers for consistent formatting
        status_icons = {
            "published": "🟢",
            "draft": "🟡",
            "archived": "🔴",
        }

        def _status_icon(status: str | None) -> str:
            return status_icons.get((status or "").lower(), "⚪")

        def _short_summary(text: str | None) -> str:
            if not text:
                return ""
            clean = " ".join(text.split())
            return textwrap.shorten(clean, width=180, placeholder="…")

        # Filter controls
        relation_types = sorted(list(set(rel["relation_type"] for rel in relations)))
        with st.container(border=True):
            st.markdown("**Filters**")
            col_type, col_search = st.columns([1, 2])
            with col_type:
                relation_type_filter = st.selectbox(
                    "Relatietype",
                    options=["Alle types"] + relation_types,
                    key="relations_type_filter"
                )
            with col_search:
                search_term = st.text_input(
                    "Zoek op titel of samenvatting",
                    key="relations_search",
                    placeholder="Bijv. zorgplan"
                )
            st.caption("Pas filters toe om specifieke relaties sneller terug te vinden.")

        # Filter relations
        filtered_relations = relations

        if relation_type_filter != "Alle types":
            filtered_relations = [
                rel for rel in filtered_relations
                if rel["relation_type"] == relation_type_filter
            ]

        if search_term:
            lowered = search_term.lower()
            filtered_relations = [
                rel for rel in filtered_relations
                if lowered in rel["source_title"].lower()
                or lowered in rel["target_title"].lower()
                or lowered in (rel.get("source_summary") or "").lower()
                or lowered in (rel.get("target_summary") or "").lower()
            ]

        if not filtered_relations:
            st.warning("Geen relaties gevonden met de huidige filters.")
            return

        st.markdown(f"**Getoond:** {len(filtered_relations)} van {len(relations)} relaties")

        # Group by relation type for better organization
        relations_by_type = {}
        for relation in filtered_relations:
            rel_type = relation["relation_type"]
            if rel_type not in relations_by_type:
                relations_by_type[rel_type] = []
            relations_by_type[rel_type].append(relation)

        # Display relations grouped by type
        for rel_type in sorted(relations_by_type.keys()):
            relations_list = relations_by_type[rel_type]
            with st.expander(f"🔗 {rel_type.title()} ({len(relations_list)})", expanded=True):
                for relation in relations_list:
                    source_title = relation.get("source_title") or "(zonder titel)"
                    target_title = relation.get("target_title") or "(zonder titel)"

                    with st.container(border=True):
                        col_source, col_meta, col_target = st.columns([3, 1, 3])

                        with col_source:
                            st.markdown(
                                f"{_status_icon(relation.get('source_status'))} **{source_title}**"
                            )
                            st.caption(
                                f"ID: `{relation['source_id'][:8]}...` | Status: {relation.get('source_status', 'onbekend')}"
                            )
                            summary = _short_summary(relation.get("source_summary"))
                            if summary:
                                st.caption(summary)

                        with col_meta:
                            badge_html = (
                                "<div style='text-align:center;'>"
                                "<div style='font-size:2rem; line-height:1; margin-bottom:4px;'>→</div>"
                                f"<span style='display:inline-block; background-color:#eef2ff; color:#1f3b8c; padding:4px 10px; "
                                "border-radius:999px; font-size:0.75rem; font-weight:600;'>"
                                f"{rel_type.title()}"
                                "</span>"
                                "</div>"
                            )
                            st.markdown(badge_html, unsafe_allow_html=True)

                        with col_target:
                            st.markdown(
                                f"{_status_icon(relation.get('target_status'))} **{target_title}**"
                            )
                            st.caption(
                                f"ID: `{relation['target_id'][:8]}...` | Status: {relation.get('target_status', 'onbekend')}"
                            )
                            summary = _short_summary(relation.get("target_summary"))
                            if summary:
                                st.caption(summary)

                st.caption("Selecteer een relatietype om details te verkennen.")

    except Exception as exc:
        st.error(f"Fout bij ophalen relaties: {exc}")

# --- UI: Relatiegrafiek-tab met streamlit-agraph --------------------------------
# Vereist: pip install streamlit-agraph


def _render_relations_graph_tab(service: KnowledgeService) -> None:
    st.markdown("### Relatiegrafiek")

    # Controls
    col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
    with col1:
        limit = st.number_input("Limiet", 20, 1000, 200, 20, key="graph_limit")
    with col2:
        physics = st.toggle("Physics", value=True, key="graph_physics")
    with col3:
        hierarchical = st.toggle("Hiërarchisch", value=False, key="graph_hier")
    with col4:
        directed = st.toggle("Gericht", value=True, key="graph_directed")

    # Data
    relations = service.list_all_relations(limit=limit)
    notes = service.list_all_notes(limit=limit)

    # Filters
    all_types = sorted({r["relation_type"] for r in relations})
    active_types = st.multiselect(
        "Filter relation types",
        options=all_types,
        default=all_types,
        key="graph_type_filter",
    )

    # Build nodes en edges
    nodes_map: dict[str, Node] = {}
    edges: list[Edge] = []

    def _add_node(note_id: str, title: str, status: str, summary: str | None) -> None:
        if note_id in nodes_map:
            return
        label = title or "(zonder titel)"
        tooltip = (summary or "").strip() or label
        nodes_map[note_id] = Node(
            id=note_id,
            label=label,
            title=tooltip,
            group=status.lower(),
            size=18,
            shape="dot",
        )

    # Eerst alle notities toevoegen
    for n in notes:
        _add_node(n.id, n.title, n.status, n.summary)

    # Dan relaties toevoegen
    for rel in relations:
        if rel["relation_type"] not in active_types:
            continue
        _add_node(
            rel["source_id"], rel.get("source_title", ""), rel.get("source_status", "unknown"), rel.get("source_summary")
        )
        _add_node(
            rel["target_id"], rel.get("target_title", ""), rel.get("target_status", "unknown"), rel.get("target_summary")
        )
        edges.append(
            Edge(
                source=rel["source_id"],
                target=rel["target_id"],
                label=rel["relation_type"],
                **({"arrows": "to"} if directed else {}),
            )
        )

    # Config
    config = Config(
        width=900,
        height=700,
        directed=directed,
        physics=physics,
        hierarchical=hierarchical,
        nodeHighlightBehavior=True,
        highlightColor="#F7A7A6",
        collapsible=True,
    )

    _ = agraph(nodes=list(nodes_map.values()), edges=edges, config=config)
