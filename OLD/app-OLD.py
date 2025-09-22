import streamlit as st

from services.knowledge import KnowledgeService
from ui import create_note_tab, manage_tab, search_chat_tab

st.set_page_config(page_title="Kennisbank Zorgwaard", layout="wide")
st.title("Kennisbank Zorgwaard")

service = KnowledgeService()

tabs = st.tabs(["Vraag", "Opslaan", "Beheer"])

with tabs[0]:
    search_chat_tab.render(service)

with tabs[1]:
    create_note_tab.render(service)

with tabs[2]:
    manage_tab.render(service)
