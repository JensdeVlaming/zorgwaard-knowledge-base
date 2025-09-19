import streamlit as st
from db import upsert_entry, query_index, list_embeddings_snapshot, suggest_supersedes
from llm import answer_from_context, summarize_and_tag

st.set_page_config(page_title="Kennisbank Zorgwaard", layout="wide")
st.title("Kennisbank Zorgwaard")

tabs = st.tabs(["Vraag", "Opslaan", "Beheer"])

# --- Vraag-tab ---
with tabs[0]:
    st.subheader("Vraag stellen")
    vraag = st.text_input("Wat wil je weten?", placeholder="Bijvoorbeeld: Hoe maak ik een Knox-account aan?")

    if st.button("Zoeken"):
        res = query_index(vraag)
        matches = res.get("matches", [])
        out = answer_from_context(vraag, matches)

        col1, col2 = st.columns([2, 1])

        with col1:
            st.markdown("#### Antwoord")
            st.info(out["answer"])   # netjes leesbaar in een info-box
            with st.expander("Denkspoor"):
                st.json(out["trace"])

        with col2:
            st.markdown("#### Bronnen")
            for i, m in enumerate(matches):
                md = m.get("metadata", {})
                with st.expander(f"[{i+1}] {md.get('topic','')} – {md.get('date','')}"):
                    st.write("**Samenvatting:**")
                    st.write(md.get("summary",""))
                    st.write("**Tags:**")
                    st.caption(md.get("tags",""))
                    st.write("**Tekst:**")
                    st.caption(md.get("text",""))
                    st.write("**Door:**", md.get("created_by",""))

# --- Opslaan-tab ---
with tabs[1]:
    st.subheader("Nieuwe kennis toevoegen")
    text = st.text_area("Inhoud")
    topic = st.text_input("Onderwerp")
    created_by = st.text_input("Aangemaakt door")

    if "related_ids" not in st.session_state: st.session_state["related_ids"] = []
    if "supersedes_ids" not in st.session_state: st.session_state["supersedes_ids"] = []
    if "suggestions" not in st.session_state: st.session_state["suggestions"] = []

    if st.button("Zoek mogelijke matches"):
        st.session_state["suggestions"] = suggest_supersedes(text)

    if st.session_state["suggestions"]:
        st.markdown("#### 💡 Mogelijke matches")
        st.caption("Gerelateerd = inhoudelijk verwant • Supersedes = vervangt dit item")

        for s in st.session_state["suggestions"]:
            md = s["metadata"]
            sid = s["id"]
            with st.expander(f"ID={sid} | Topic={md.get('topic','')} | Score={s['score']:.2f}"):
                st.write("**Samenvatting:**", md.get("summary", ""))
                st.write("**Datum:**", md.get("date", ""))
                st.write("**Tags:**", md.get("tags", ""))
                st.info(md.get("text", ""))

                if st.checkbox("✅ Gerelateerd", key=f"rel_{sid}"):
                    st.session_state["related_ids"].append(sid)
                if st.checkbox("⚠️ Supersedes", key=f"sup_{sid}"):
                    st.session_state["supersedes_ids"].append(sid)

    if st.button("Opslaan"):
        if not text.strip():
            st.error("Voer tekst in.")
        else:
            at = summarize_and_tag(text)
            rid = upsert_entry(
                text,
                topic,
                at["tags"],
                at["summary"],
                created_by=created_by or "onbekend",
                related_to=st.session_state["related_ids"],
                supersedes=st.session_state["supersedes_ids"],
            )
            st.success(f"✅ Opgeslagen met ID: {rid}")
            st.session_state["related_ids"] = []
            st.session_state["supersedes_ids"] = []
            st.session_state["suggestions"] = []

# --- Beheer-tab ---
with tabs[2]:
    st.subheader("Beheer")
    df = list_embeddings_snapshot()
    if df.empty:
        st.info("Geen documenten gevonden.")
    else:
        st.dataframe(df, use_container_width=True, height=600)