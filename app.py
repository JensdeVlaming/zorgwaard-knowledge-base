import streamlit as st

from services.knowledge import KnowledgeService
from ui import manage_tab, question_tab, save_tab

st.set_page_config(page_title="Kennisbank Zorgwaard", layout="wide")
st.title("Kennisbank Zorgwaard")

service = KnowledgeService()

tabs = st.tabs(["Vraag", "Opslaan", "Beheer"])

with tabs[0]:
    question_tab.render(service)

with tabs[1]:
    save_tab.render(service)

with tabs[2]:
    manage_tab.render(service)
