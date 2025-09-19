from __future__ import annotations

import streamlit as st

from services.knowledge import KnowledgeService


def render(service: KnowledgeService) -> None:
    st.subheader("Beheer")
    df = service.list_documents()
    if df.empty:
        st.info("Geen documenten gevonden.")
        return
    st.dataframe(df, width="stretch", height=600)
