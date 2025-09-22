import streamlit as st

from core.db_client import init_db
from ui import create_note_tab, search_tab

st.set_page_config(page_title="Zorgwaard Kennisbank", layout="wide")
st.title("Zorgwaard Kennisbank")


@st.cache_resource
def _bootstrap_db() -> bool:
    init_db()
    return True


_bootstrap_db()

tabs = st.tabs(["Zoeken", "Notitie toevoegen", "Alle notities"])

with tabs[0]:
    search_tab.render()

with tabs[1]:
    create_note_tab.render()

with tabs[2]:
    from ui.list_notes_tab import render

    render()
