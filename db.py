import uuid
import pandas as pd
import streamlit as st
from datetime import datetime
from typing import List, Dict, Any, Optional
from config import index, EMBED_DIM
from llm import embed_text


def suggest_supersedes(text: str, threshold: float = 0.4, top_k: int = 5) -> List[Dict[str, Any]]:
    emb = embed_text(text)
    if emb is None:
        return []
    candidates = []
    try:
        res = index.query(vector=emb, top_k=top_k, include_metadata=True)
        for m in res.get("matches", []):
            score = m.get("score", 0)
            if score >= threshold:
                candidates.append({
                    "id": m.get("id"),
                    "score": score,
                    "metadata": m.get("metadata", {})
                })
    except Exception as e:
        st.warning(f"Suggestie-check fout: {e}")
    return candidates


def upsert_entry(
    text: str,
    topic: str,
    tags: List[str],
    summary: str,
    created_by: str,
    supersedes: Optional[List[str]] = None,
    related_to: Optional[List[str]] = None,
    entry_id: Optional[str] = None,
):
    emb = embed_text(text)
    if emb is None:
        st.error("❌ Geen embedding gegenereerd.")
        return None

    entry_id = entry_id or str(uuid.uuid4())

    # metadata nieuwe entry
    md = {
        "topic": topic,
        "summary": summary,
        "tags": ",".join(tags),
        "date": datetime.now().isoformat(timespec="seconds"),
        "created_by": created_by,
        "text": text,
    }

    if related_to:
        md["related_to"] = ",".join(sorted(set(related_to)))
    if supersedes:
        md["supersedes"] = ",".join(sorted(set(supersedes)))

    # sla nieuwe entry op
    index.upsert([(entry_id, emb, md)])

    # update oude documenten met superseded_by (voorkom duplicaten)
    if supersedes:
        for sid in supersedes:
            try:
                res = index.fetch(ids=[sid])
                if sid in res.vectors:
                    old_meta = res.vectors[sid].metadata or {}
                    existing = set((old_meta.get("superseded_by") or "").split(","))
                    existing.add(entry_id)
                    old_meta["superseded_by"] = ",".join(sorted([x for x in existing if x]))
                    # zelfde vector behouden, alleen metadata aanpassen
                    index.upsert([(sid, res.vectors[sid].values, old_meta)])
            except Exception as e:
                st.warning(f"Kon superseded_by niet instellen voor {sid}: {e}")

    # update gerelateerde documenten (bidirectioneel, ook sets)
    if related_to:
        for rid in related_to:
            try:
                res = index.fetch(ids=[rid])
                if rid in res.vectors:
                    old_meta = res.vectors[rid].metadata or {}
                    existing = set((old_meta.get("related_to") or "").split(","))
                    existing.add(entry_id)
                    old_meta["related_to"] = ",".join(sorted([x for x in existing if x]))
                    index.upsert([(rid, res.vectors[rid].values, old_meta)])
            except Exception as e:
                st.warning(f"Kon related_to niet instellen voor {rid}: {e}")

    return entry_id


def query_index(question: str, top_k: int = 5, filter: Dict[str, Any] = None, expand_related: bool = True):
    """Zoek in de index en haal optioneel ook related_to, supersedes en superseded_by entries erbij."""
    q_emb = embed_text(question)
    if q_emb is None:
        return {"matches": []}

    res = index.query(vector=q_emb, top_k=top_k, include_metadata=True, filter=filter)

    if expand_related:
        extra_matches = []
        seen_ids = set(m.get("id") for m in res.get("matches", []))

        for m in res.get("matches", []):
            md = m.get("metadata", {}) or {}

            related_ids = [rid.strip() for rid in (md.get("related_to", "") or "").split(",") if rid.strip()]
            supersedes_ids = [sid.strip() for sid in (md.get("supersedes", "") or "").split(",") if sid.strip()]
            superseded_by_ids = [sid.strip() for sid in (md.get("superseded_by", "") or "").split(",") if sid.strip()]

            # related_to
            for rid in related_ids:
                if rid not in seen_ids:
                    try:
                        rel = index.fetch(ids=[rid])
                        for vid, vec in rel.vectors.items():
                            extra_matches.append({
                                "id": vid,
                                "metadata": vec.metadata or {},
                                "relation": "related_to"
                            })
                            seen_ids.add(vid)
                    except Exception as e:
                        st.warning(f"Kon related {rid} niet ophalen: {e}")

            # supersedes
            for sid in supersedes_ids:
                if sid not in seen_ids:
                    try:
                        rel = index.fetch(ids=[sid])
                        for vid, vec in rel.vectors.items():
                            extra_matches.append({
                                "id": vid,
                                "metadata": vec.metadata or {},
                                "relation": "supersedes"
                            })
                            seen_ids.add(vid)
                    except Exception as e:
                        st.warning(f"Kon supersedes {sid} niet ophalen: {e}")

            # superseded_by
            for sbid in superseded_by_ids:
                if sbid not in seen_ids:
                    try:
                        rel = index.fetch(ids=[sbid])
                        for vid, vec in rel.vectors.items():
                            extra_matches.append({
                                "id": vid,
                                "metadata": vec.metadata or {},
                                "relation": "superseded_by"
                            })
                            seen_ids.add(vid)
                    except Exception as e:
                        st.warning(f"Kon superseded_by {sbid} niet ophalen: {e}")

        res["matches"].extend(extra_matches)

    return res

def list_embeddings_snapshot(limit=2000) -> pd.DataFrame:
    stats = index.describe_index_stats()
    namespaces = stats.get("namespaces", {}) or {"": {"vector_count": stats.get("total_vector_count", 0)}}
    rows = []
    for ns in namespaces:
        count = namespaces[ns]["vector_count"]
        if count == 0:
            continue
        res = index.query(
            vector=[0.0] * EMBED_DIM,
            top_k=min(count, limit),
            namespace=ns if ns else None,
            include_metadata=True
        )
        for m in res.get("matches", []):
            md = m.get("metadata", {}) or {}

            # normaliseer velden die meerdere IDs kunnen bevatten
            related_list = (md.get("related_to") or "").split(",") if md.get("related_to") else []
            supersedes_list = (md.get("supersedes") or "").split(",") if md.get("supersedes") else []
            superseded_by_list = (md.get("superseded_by") or "").split(",") if md.get("superseded_by") else []

            rows.append({
                "ID": m.get("id", ""),
                "Topic": md.get("topic", ""),
                "Date": md.get("date", ""),
                "Tags": md.get("tags", ""),
                "Summary": md.get("summary", ""),
                "Text": md.get("text", ""),
                "Related_to": related_list,
                "Supersedes": supersedes_list,
                "Superseded_by": superseded_by_list,
                "Created_by": md.get("created_by", ""),
            })
    return pd.DataFrame(rows)

def update_record(entry_id: str, new_metadata: Dict[str, Any], keep_vector: bool = True):
    """Werk metadata van een record bij. 
       Als keep_vector=True, behoudt de oude vector."""
    try:
        # Eerst ophalen om de vector te behouden
        if keep_vector:
            res = index.fetch(ids=[entry_id])
            vec = None
            for vid, v in res.vectors.items():
                vec = v.values  # bestaande vector
            if vec is None:
                return False
            index.upsert([(entry_id, vec, new_metadata)])
        else:
            # zonder vector bijwerken vereist dat je zelf een nieuwe embedding meegeeft
            index.upsert([(entry_id, embed_text(new_metadata.get("text", "")), new_metadata)])
        return True
    except Exception as e:
        st.error(f"❌ Update fout: {e}")
        return False
