import streamlit as st

from ui import create_note_tab, search_tab

st.set_page_config(page_title="Zorgwaard Kennisbank", layout="wide")
st.title("📚 Zorgwaard Kennisbank")

tabs = st.tabs(["Zoeken", "Notitie toevoegen", "Alle notities"])

with tabs[0]:
    search_tab.render()

with tabs[1]:
    create_note_tab.render()

with tabs[2]:
    from ui.list_notes_tab import render

    render()
