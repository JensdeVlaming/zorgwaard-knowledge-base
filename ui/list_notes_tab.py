import streamlit as st
from streamlit_agraph import Config, Edge, Node, agraph

from infrastructure.llm.llm_utils import embed_text
from services.note_service import delete_note, get_note, list_notes
from services.relation_service import (
    create_relation_entry,
    delete_relation,
    list_relations_for_note,
    list_relations_for_notes,
    suggest_relations_for_embedding,
    update_relation_type,
)

STATUS_LABELS = {
    "draft": "Concept",
    "published": "Gepubliceerd",
    "archived": "Archief",
}

STATUS_COLORS = {
    "draft": "#64B5F6",
    "published": "#81C784",
    "archived": "#BCAAA4",
}

RELATION_TYPE_LABELS = {
    "supports": "Ondersteunt",
    "contradicts": "Spreekt tegen",
    "supersedes": "Vervangt",
    "related": "Gerelateerd",
    "duplicate": "Duplicaat",
}

RELATION_COLORS = {
    "supports": "#66BB6A",
    "contradicts": "#EF5350",
    "supersedes": "#FFB74D",
    "related": "#9575CD",
    "duplicate": "#4DD0E1",
}

STATUS_DISPLAY_ORDER = ["draft", "published", "archived"]
STATUS_DISPLAY_OPTIONS = [
    STATUS_LABELS.get(status, status) for status in STATUS_DISPLAY_ORDER
]

DEFAULT_RELATION_LABEL = "Geen relatie"

RELATION_TYPE_ORDER = [
    "supports",
    "contradicts",
    "supersedes",
    "related",
    "duplicate",
]
RELATION_TYPE_OPTIONS = [
    DEFAULT_RELATION_LABEL,
    *[RELATION_TYPE_LABELS.get(value, value) for value in RELATION_TYPE_ORDER],
]
RELATION_LABEL_TO_TYPE = {label: key for key, label in RELATION_TYPE_LABELS.items()}
RELATION_LABEL_TO_TYPE[DEFAULT_RELATION_LABEL] = ""

DIRECTION_OPTIONS = {
    "outgoing": "Deze notitie → andere",
    "incoming": "Andere → deze notitie",
}

RELATION_HELP_TEXT = """
<div style='line-height:1.2; font-size:0.9em; color:gray; margin-bottom:10px;'>
<b>Ondersteunt</b> – bevestigt of versterkt andere notitie (bv. handleiding bevestigt procedure)<br>
<b>Spreekt tegen</b> – inhoud is tegenstrijdig (bv. A zegt RAM IT, B zegt Zorgwaard)<br>
<b>Vervangt</b> – nieuwe versie vervangt de oude (bv. Knox v3 vervangt Knox v2)<br>
<b>Gerelateerd</b> – zelfde thema, geen bewijs (bv. Knox-account vs MFA-procedure)<br>
<b>Duplicaat</b> – inhoud (bijna) hetzelfde
</div>
"""


def format_status(value: str | None) -> str:
    key = value if value is not None else "-"
    return STATUS_LABELS.get(key, key)


def format_datetime(value) -> str:
    if not value:
        return "-"
    return value.strftime("%d-%m-%Y %H:%M")


def render() -> None:
    filter_col, limit_col = st.columns([3, 1])
    with filter_col:
        query = (
            st.text_input(
                "Zoek (titel, samenvatting, auteur)",
                placeholder="Bijv. onboarding of wijkteam",
            )
            .strip()
            .lower()
        )
    with limit_col:
        limit = int(
            st.number_input(
                "Aantal te laden",
                min_value=5,
                max_value=500,
                value=50,
                step=5,
            )
        )

    notes = list_notes(limit=limit)

    if not notes:
        st.info("Nog geen notities gevonden.")
        return

    available_statuses = sorted(
        {format_status(str(note.status)) for note in notes if note.status is not None}
    )
    selected_statuses = (
        st.multiselect(
            "Filter op status",
            options=available_statuses,
            default=available_statuses,
        )
        if available_statuses
        else []
    )

    filtered_notes = []
    for note in notes:
        status_label = format_status(str(note.status))
        if selected_statuses and status_label not in selected_statuses:
            continue

        searchable_fields = [
            (note.title or "").lower(),
            (note.summary or "").lower(),
            (note.author or "").lower(),
        ]
        if query and not any(query in field for field in searchable_fields):
            continue

        filtered_notes.append(note)

    notes_tab, graph_tab = st.tabs(["Notities", "Relaties"])

    with notes_tab:
        st.caption(f"{len(filtered_notes)} van {len(notes)} notities getoond")

        data = [
            {
                "Selecteer": False,
                "Titel": note.title,
                "Auteur": note.author,
                "Status": format_status(note.status),
                "Aangemaakt": format_datetime(note.created_at),
                "Bijgewerkt": format_datetime(note.updated_at),
                "Samenvatting": note.summary,
            }
            for note in filtered_notes
        ]

        data_view = st.data_editor(
            data,
            column_order=[
                "Selecteer",
                "Titel",
                "Auteur",
                "Status",
                "Samenvatting",
            ],  # visible by default
            hide_index=True,
            width="stretch",
            column_config={
                "Selecteer": st.column_config.CheckboxColumn(
                    label="", disabled=False, width=10
                ),
                "Titel": st.column_config.TextColumn("Titel", width=200, disabled=True),
                "Auteur": st.column_config.TextColumn(
                    "Auteur", width=50, disabled=True
                ),
                "Status": st.column_config.TextColumn(
                    "Status", width="small", disabled=True
                ),
                "Samenvatting": st.column_config.TextColumn(
                    "Samenvatting", width="large", disabled=True
                ),
                "Aangemaakt": st.column_config.TextColumn("Aangemaakt", disabled=True),
                "Bijgewerkt": st.column_config.TextColumn("Bijgewerkt", disabled=True),
            },
        )
        selected_indices = [
            idx for idx, row in enumerate(data_view) if row.get("Selecteer")
        ]

        if selected_indices:
            selected_note = filtered_notes[selected_indices[0]]
            _render_note_detail(selected_note, notes)
        else:
            st.caption("Selecteer een notitie om details te zien of te bewerken.")

    with graph_tab:
        st.caption("Bekijk relaties tussen de gefilterde notities.")
        _render_relations_graph(filtered_notes)


def _render_note_detail(note, all_notes: list) -> None:
    note_id = str(getattr(note, "id", ""))

    form_container, relation_container = st.columns([5, 3])

    with form_container:
        st.markdown("### Notitie")
        title_col, author_col = st.columns([3, 1])
        title_col.text_input(
            "Titel",
            value=note.title or "",
            key=f"detail-title-{note_id}",
            disabled=True,
        )
        author_col.text_input(
            "Auteur",
            value=note.author or "",
            key=f"detail-author-{note_id}",
            disabled=True,
        )
        st.text_area(
            "Inhoud",
            value=note.content or "",
            height=220,
            key=f"detail-content-{note_id}",
            disabled=True,
        )

        status_display = format_status(note.status)
        status_options = STATUS_DISPLAY_OPTIONS or [status_display]
        try:
            status_index = status_options.index(status_display)
        except ValueError:
            status_index = 0

        st.selectbox(
            "Status",
            status_options,
            index=status_index,
            key=f"detail-status-{note_id}",
            disabled=True,
        )

        st.text_area(
            "Samenvatting",
            value=note.summary or "",
            height=120,
            key=f"detail-summary-{note_id}",
            disabled=True,
        )

        st.caption(f"Aangemaakt: {format_datetime(note.created_at)}")
        st.caption(f"Bijgewerkt: {format_datetime(note.updated_at)}")

        st.divider()
        st.markdown("### Acties")
        st.caption(
            "Verwijderen is definitief en verwijdert ook onderliggende relaties en metadata."
        )
        confirm_key = f"confirm-delete-{note_id}"
        confirmed = st.checkbox(
            "Ik wil deze notitie permanent verwijderen",
            key=confirm_key,
        )

        if st.button(
            "Verwijder notitie",
            key=f"delete-note-{note_id}",
            type="primary",
        ):
            if not confirmed:
                st.warning("Bevestig eerst dat de notitie verwijderd mag worden.")
            elif not note_id:
                st.error("Notitie-id ontbreekt, kan niet verwijderen.")
            else:
                try:
                    delete_note(note_id)
                except ValueError as exc:
                    st.error(f"Kon notitie niet verwijderen: {exc}")
                except (
                    Exception
                ) as exc:  # pragma: no cover - defensief voor UI feedback
                    st.error(f"Onverwachte fout bij verwijderen: {exc}")
                else:
                    st.success("Notitie verwijderd.")
                    st.session_state.pop(confirm_key, None)
                    st.rerun()

    with relation_container:
        st.markdown("### Relaties")
        relations = list_relations_for_note(note_id)
        st.caption(
            "Pas hier bestaande relaties aan of voeg nieuwe relaties toe. De pijlen tonen of deze notitie bron of doel is."
        )

        note_lookup = {
            str(getattr(current, "id", "")): current
            for current in all_notes
            if getattr(current, "id", None)
        }

        for relation in relations:
            _render_relation_editor_entry(note_id, relation, note_lookup)

        if not relations:
            st.caption("Geen bestaande relaties voor deze notitie.")

        existing_pairs = {
            (
                str(getattr(relation, "source_note_id", "")),
                str(getattr(relation, "target_note_id", "")),
            )
            for relation in relations
        }

        _render_new_relation_section(note, relations, note_lookup, existing_pairs)


def _render_relation_editor_entry(
    current_note_id: str, relation, note_lookup: dict
) -> None:
    relation_id = str(getattr(relation, "id", ""))
    relation_key = (getattr(relation, "relation_type", "") or "").strip()

    is_outgoing = str(getattr(relation, "source_note_id", "")) == current_note_id
    other_note_id = (
        str(getattr(relation, "target_note_id", ""))
        if is_outgoing
        else str(getattr(relation, "source_note_id", ""))
    )

    other_note = note_lookup.get(other_note_id)
    if other_note is None and other_note_id:
        fetched = get_note(other_note_id)
        if fetched:
            note_lookup[other_note_id] = fetched
            other_note = fetched

    other_title = (
        getattr(other_note, "title", None) or f"Notitie {other_note_id}".strip()
    )
    other_summary = (
        getattr(other_note, "summary", None) or "Geen samenvatting beschikbaar."
    )
    other_status = (
        format_status(getattr(other_note, "status", None)) if other_note else None
    )

    relation_label = RELATION_TYPE_LABELS.get(
        relation_key, relation_key or RELATION_TYPE_OPTIONS[0]
    )
    try:
        relation_index = RELATION_TYPE_OPTIONS.index(relation_label)
    except ValueError:
        relation_index = 0

    direction_hint = "Deze notitie →" if is_outgoing else "→ Deze notitie"
    expander_title = f"{other_title} • {relation_label}"

    with st.expander(expander_title, expanded=False):
        st.caption(other_summary)
        st.caption(f"Richting: {direction_hint}")
        if other_status:
            st.caption(f"Status: {other_status}")

        selected_label = st.selectbox(
            "Relatie",
            RELATION_TYPE_OPTIONS,
            index=relation_index,
            key=f"relation-select-{relation_id}",
        )

        st.markdown(RELATION_HELP_TEXT, unsafe_allow_html=True)

        action_col, delete_col = st.columns(2)
        if action_col.button("Opslaan", key=f"relation-save-{relation_id}"):
            new_type = RELATION_LABEL_TO_TYPE.get(selected_label)
            if not new_type:
                st.warning("Kies een geldig relatietype.")
            elif new_type == relation_key:
                st.info("Geen wijzigingen om op te slaan.")
            else:
                try:
                    update_relation_type(relation_id, new_type)
                    st.success("Relatie bijgewerkt.")
                except ValueError as exc:
                    st.error(f"Kon relatie niet bijwerken: {exc}")
                else:
                    st.rerun()

        if delete_col.button("Verwijder", key=f"relation-delete-{relation_id}"):
            try:
                delete_relation(relation_id)
                st.success("Relatie verwijderd.")
            except ValueError as exc:
                st.error(f"Kon relatie niet verwijderen: {exc}")
            else:
                st.rerun()


def _render_new_relation_section(
    note,
    relations: list,
    note_lookup: dict,
    existing_pairs: set,
) -> None:
    note_id = str(getattr(note, "id", ""))

    st.markdown("#### Nieuwe relaties")

    if not note_id:
        st.caption("Notitie-id ontbreekt, kan geen relaties toevoegen.")
        return

    content = getattr(note, "content", "") or ""
    if not content.strip():
        st.caption("Geen inhoud beschikbaar om relaties te suggereren.")
        return

    suggestions = _load_relation_suggestions(note)

    existing_partner_ids = {
        str(getattr(relation, "target_note_id", ""))
        for relation in relations
        if str(getattr(relation, "target_note_id", ""))
        and str(getattr(relation, "target_note_id", "")) != note_id
    }
    existing_partner_ids.update(
        {
            str(getattr(relation, "source_note_id", ""))
            for relation in relations
            if str(getattr(relation, "source_note_id", ""))
            and str(getattr(relation, "source_note_id", "")) != note_id
        }
    )

    filtered_suggestions = []
    seen_ids = set()
    for suggestion in suggestions:
        suggestion_id = str(getattr(suggestion, "note_id", ""))
        if (
            not suggestion_id
            or suggestion_id == note_id
            or suggestion_id in seen_ids
            or suggestion_id in existing_partner_ids
            or (note_id, suggestion_id) in existing_pairs
            or (suggestion_id, note_id) in existing_pairs
        ):
            continue
        seen_ids.add(suggestion_id)
        filtered_suggestions.append(suggestion)

    if not filtered_suggestions:
        st.caption("Geen relatie-suggesties beschikbaar.")
        return

    _sync_new_relation_state(note_id, filtered_suggestions)

    base_state_key = f"existing-rel-{note_id}"
    for suggestion in filtered_suggestions:
        suggestion_id = str(suggestion.note_id)
        base_key = f"{base_state_key}-{suggestion_id}"
        relation_select_key = f"{base_key}-type"
        direction_key = f"{base_key}-direction"

        relation_label = st.session_state.get(
            relation_select_key, DEFAULT_RELATION_LABEL
        )
        direction_value = st.session_state.get(direction_key, "outgoing")

        with st.expander(
            f"{suggestion.title or '(geen titel)'} • {suggestion.score:.2f}",
            expanded=False,
        ):
            st.caption(suggestion.summary or "Geen samenvatting beschikbaar.")
            st.caption(f"Status: {format_status(suggestion.status)}")

            st.selectbox(
                "Relatie",
                RELATION_TYPE_OPTIONS,
                key=relation_select_key,
            )
            st.radio(
                "Richting",
                options=list(DIRECTION_OPTIONS.keys()),
                key=direction_key,
                format_func=lambda option: DIRECTION_OPTIONS[option],
                horizontal=True,
            )

            st.markdown(RELATION_HELP_TEXT, unsafe_allow_html=True)

            if st.button("Relatie toevoegen", key=f"relation-add-{suggestion_id}"):
                relation_value = RELATION_LABEL_TO_TYPE.get(relation_label)
                if not relation_value:
                    st.warning("Kies eerst een relatietype.")
                    return

                source_id = note_id if direction_value == "outgoing" else suggestion_id
                target_id = suggestion_id if direction_value == "outgoing" else note_id

                try:
                    create_relation_entry(
                        source_note_id=source_id,
                        target_note_id=target_id,
                        relation_type=relation_value,
                    )
                except ValueError as exc:
                    st.error(f"Kon relatie niet aanmaken: {exc}")
                except (
                    Exception
                ) as exc:  # pragma: no cover - defensief, toont foutmelding in UI
                    st.error(f"Onverwachte fout bij opslaan: {exc}")
                else:
                    _clear_new_relation_state_entry(note_id, suggestion_id)
                    st.success("Relatie toegevoegd.")
                    st.rerun()


def _load_relation_suggestions(note) -> list:
    note_id = str(getattr(note, "id", ""))
    content = getattr(note, "content", "") or ""
    updated_at = getattr(note, "updated_at", None)

    if not note_id or not content.strip():
        return []

    cache = st.session_state.setdefault("existing-note-suggestion-cache", {})
    cache_entry = cache.get(note_id)
    signature = {
        "content": content,
        "updated": str(updated_at) if updated_at else None,
    }

    if (
        cache_entry
        and cache_entry.get("content") == signature["content"]
        and cache_entry.get("updated") == signature["updated"]
    ):
        return cache_entry.get("suggestions", [])

    try:
        embedding = embed_text(content)
    except Exception as exc:  # pragma: no cover - toont fout in UI
        st.error(f"Kon relatiesuggesties niet genereren: {exc}")
        return []

    if not embedding:
        return []

    suggestions = suggest_relations_for_embedding(embedding, limit=10)

    cache[note_id] = {
        "content": signature["content"],
        "updated": signature["updated"],
        "suggestions": suggestions,
    }

    return suggestions


def _sync_new_relation_state(note_id: str, suggestions: list) -> None:
    base_state_key = f"existing-rel-{note_id}"
    tracked_keys = set(st.session_state.get(f"{base_state_key}-keys", []))
    current_keys = {
        f"{base_state_key}-{getattr(suggestion, 'note_id', '')}"
        for suggestion in suggestions
    }

    for stale_key in tracked_keys - current_keys:
        st.session_state.pop(f"{stale_key}-type", None)
        st.session_state.pop(f"{stale_key}-direction", None)

    for key in current_keys:
        st.session_state.setdefault(f"{key}-type", DEFAULT_RELATION_LABEL)
        st.session_state.setdefault(f"{key}-direction", "outgoing")

    st.session_state[f"{base_state_key}-keys"] = list(current_keys)


def _clear_new_relation_state_entry(note_id: str, suggestion_id: str) -> None:
    base_state_key = f"existing-rel-{note_id}"
    entry_key = f"{base_state_key}-{suggestion_id}"

    st.session_state.pop(f"{entry_key}-type", None)
    st.session_state.pop(f"{entry_key}-direction", None)

    keys = set(st.session_state.get(f"{base_state_key}-keys", []))
    if entry_key in keys:
        keys.remove(entry_key)
        st.session_state[f"{base_state_key}-keys"] = list(keys)


def _render_relations_graph(notes: list) -> None:
    if not notes:
        st.caption("Geen notities om te visualiseren.")
        return

    note_ids = [str(note.id) for note in notes if getattr(note, "id", None)]
    if not note_ids:
        st.caption("Geen notitie-identificaties gevonden.")
        return

    relations = list_relations_for_notes(note_ids)
    note_lookup = {str(note.id): note for note in notes if getattr(note, "id", None)}

    nodes = []
    for note_id, note in note_lookup.items():
        status_value = (note.status or "").strip()
        nodes.append(
            Node(
                id=note_id,
                label=note.title or "(geen titel)",
                size=22,
                color=STATUS_COLORS.get(status_value, "#90A4AE"),
                font={"color": "#CCCCCC", "size": 14},
                title=(
                    f"Title: {note.title or '-'}\n"
                    f"Status: {format_status(status_value or None)}\n"
                    f"Auteur: {note.author or '-'}\n"
                    f"Samenvatting: {note.summary or '-'}"
                ),
                borderWidth=1,
            )
        )

    edges = []
    for relation in relations:
        source_id = str(relation.source_note_id)
        target_id = str(relation.target_note_id)

        if source_id not in note_lookup or target_id not in note_lookup:
            continue

        relation_type = (relation.relation_type or "").strip()
        edges.append(
            Edge(
                source=source_id,
                target=target_id,
                label=RELATION_TYPE_LABELS.get(
                    relation_type, relation_type or "Relatie"
                ),
                color=RELATION_COLORS.get(relation_type, "#546E7A"),
                font={"color": "#989898", "strokeWidth": 0, "size": 10},
                width=2,
                smooth=True,
                arrows={"to": {"enabled": True, "scaleFactor": 0.6}},
            )
        )

    if not edges:
        st.caption("Geen relaties gevonden tussen de gefilterde notities.")
        return

    config = Config(
        height=700,
        width="100%",
        directed=True,
        physics=True,
        hierarchical=False,
        nodeHighlightBehavior=True,
        staticGraph=False,
        backgroundColor="#FAFAFA",
        highlightColor="#FFC107",
    )

    agraph(nodes=nodes, edges=edges, config=config)
