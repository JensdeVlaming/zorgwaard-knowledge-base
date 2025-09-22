import streamlit as st

from services.notes import list_notes

STATUS_LABELS = {
    "draft": "Concept",
    "published": "Gepubliceerd",
    "archived": "Archief",
}


def format_status(value: str | None) -> str:
    return STATUS_LABELS.get(value, value or "-")


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
        {format_status(note.status) for note in notes if note.status}
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
        status_label = format_status(note.status)
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

    st.caption(f"{len(filtered_notes)} van {len(notes)} notities getoond")

    st.dataframe(
        [
            {
                "Titel": note.title,
                "Auteur": note.author,
                "Status": format_status(note.status),
                "Aangemaakt": format_datetime(note.created_at),
                "Bijgewerkt": format_datetime(note.updated_at),
                "Samenvatting": note.summary,
            }
            for note in filtered_notes
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("### Detail")
    for note in filtered_notes:
        with st.expander(note.title or "Naamloze notitie", expanded=False):
            meta_col1, meta_col2, meta_col3 = st.columns(3)
            meta_col1.markdown(f"**Auteur:** {note.author or 'Onbekend'}")
            meta_col2.markdown(f"**Status:** {format_status(note.status)}")
            meta_col3.markdown(f"**Bijgewerkt:** {format_datetime(note.updated_at)}")

            st.markdown("**Samenvatting**")
            st.write(note.summary or "—")

            with st.expander("Bekijk volledige inhoud", expanded=False):
                st.write(note.content or "—")
