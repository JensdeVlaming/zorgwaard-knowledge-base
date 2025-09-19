import json, re
import numpy as np
import streamlit as st
from typing import List, Dict, Any, Optional
from config import client, EMBED_MODEL, CHAT_MODEL

# ---------------------
# Basisfuncties
# ---------------------
@st.cache_data(show_spinner=False)
def _cached_embed(text: str) -> Optional[List[float]]:
    try:
        res = client.embeddings.create(input=text, model=EMBED_MODEL)
        return res.data[0].embedding
    except Exception as e:
        st.error(f"Embedding fout: {e}")
        return None

def embed_text(text: str) -> Optional[List[float]]:
    return _cached_embed(text.strip())

def llm_chat(messages: List[Dict[str, str]], model: str = CHAT_MODEL) -> str:
    try:
        resp = client.chat.completions.create(model=model, messages=messages)
        return resp.choices[0].message.content
    except Exception as e:
        st.error(f"LLM fout: {e}")
        return ""

def answer_from_context(question: str, matches: List[Dict[str, Any]]) -> dict:
    # Map database-id → bronnummer
    id_to_num = {m.get("id"): str(i+1) for i, m in enumerate(matches)}

    def map_ids_to_refs(raw: str) -> list[str]:
        if not raw:
            return []
        ids = [x.strip() for x in raw.split(",") if x.strip()]
        return [f"[{id_to_num.get(x, '?')}]" for x in ids]

    def format_doc(i, m):
        md = m["metadata"]
        supersedes = map_ids_to_refs(md.get("supersedes", ""))
        superseded_by = map_ids_to_refs(md.get("superseded_by", ""))

        status = "ACTUEEL"
        notes = []
        if supersedes:
            notes.append(f"vervangt {', '.join(supersedes)}")
        if superseded_by:
            status = "VEROUDERD"
            notes.append(f"vervangen door {', '.join(superseded_by)}")

        notes_str = f" ({status}{', ' + ', '.join(notes) if notes else ''})"

        return (
            f"[{i+1}]{notes_str}\n"
            f"Topic: {md.get('topic','')}\n"
            f"Date: {md.get('date','')}\n"
            f"Tags: {md.get('tags','')}\n"
            f"Summary: {md.get('summary','')}"
        )

    sources_block = "\n\n".join(format_doc(i, m) for i, m in enumerate(matches))

    sys = {
        "role": "system",
        "content": (
            "Je bent een kennisbank-assistent.\n\n"
            "DOCUMENTRELATIES:\n"
            "- 'ACTUEEL': dit document vervangt oudere documenten en is de enige geldige hoofdbron.\n"
            "- 'VEROUDERD': dit document is vervangen door een nieuwer document. "
            "Gebruik deze alleen ter context, maar niet als hoofdbron.\n"
            "- 'related_to': inhoudelijk verwant, nooit leidend.\n\n"
            "REGELS VOOR ANTWOORDEN:\n"
            "1. Baseer je antwoord uitsluitend op de ACTUELE documenten.\n"
            "2. Voeg extra uitleg uit VEROUDERDE of RELATED documenten toe als context.\n"
            "3. Verwijs naar bronnen alleen met hun nummer [n]."
        )
    }

    usr = {"role": "user", "content": f"Vraag: {question}\n\nBronnen:\n{sources_block}"}
    answer = llm_chat([sys, usr])

    return {
        "answer": answer,
        "trace": {
            "question": question,
            "system": sys,
            "prompt": usr["content"],
            "matches": matches,
        }
    }


# ---------------------
# Geavanceerde samenvatting & tagging
# ---------------------
CONTROLLED_TAGS: List[str] = []  # optioneel vullen met canonieke tags

def _force_json(messages):
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
        temperature=0.2,
        response_format={"type": "json_object"}
    )
    raw = resp.choices[0].message.content
    return json.loads(raw)

def _split_chunks(text: str, max_chars: int = 6000) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        if len(cur) + len(p) + 2 <= max_chars:
            cur = f"{cur}\n\n{p}" if cur else p
        else:
            if cur: chunks.append(cur)
            cur = p
    if cur: chunks.append(cur)
    return chunks or [text[:max_chars]]

def _summarize_chunks(text: str) -> str:
    chunks = _split_chunks(text)
    partials = []
    for ch in chunks:
        try:
            data = _force_json([
                {"role": "system", "content": "Vat bondig samen (zorgcontext)."},
                {"role": "user", "content": "JSON: {\"summary\":\"...\"}\n\n" + ch}
            ])
            partials.append(data.get("summary","").strip())
        except Exception:
            partials.append(ch[:300])
    synth_in = "\n\n".join([f"- {s}" for s in partials if s])
    data = _force_json([
        {"role": "system", "content": "Combineer bullets tot één samenvatting."},
        {"role": "user", "content": "JSON: {\"summary\":\"...\"}\n\n" + synth_in}
    ])
    return data.get("summary","").strip()

def _llm_tag_candidates(text: str, k: int = 20) -> list[str]:
    try:
        data = _force_json([
            {"role":"system","content":"Extraheer trefwoorden voor zorg-kennisbank."},
            {"role":"user","content":f"Genereer {k} kandidaten. JSON: {{\"candidates\": [\"...\"]}}\n\n{text}"}
        ])
        return [str(c).strip().lower() for c in data.get("candidates", []) if str(c).strip()]
    except Exception:
        return []

_DUTCH_STOP = {"de","het","een","en","of","dat","die","voor","met","zonder","op","tot","van","in","uit","bij","aan","als","te","door","per","naar","om","is","zijn","wordt","worden","kan","kunnen","moet","moeten","mag","mogen","niet","wel"}
_EN_STOP = {"the","a","an","and","or","for","to","of","in","on","at","by","from","with","without","is","are","be","been","being","this","that","these","those","as","it","its","into","over"}

def _stat_tag_candidates(text: str, top_n: int = 20) -> list[str]:
    tokens = [t.lower() for t in re.findall(r"[a-zA-ZÀ-ÿ0-9\-]+", text)]
    toks = [t for t in tokens if t not in _DUTCH_STOP and t not in _EN_STOP and len(t) > 2]
    freq = {}
    for t in toks: freq[t] = freq.get(t, 0) + 1
    for i in range(len(toks)-1):
        big = f"{toks[i]} {toks[i+1]}"
        freq[big] = freq.get(big, 0) + 1.5
    for i in range(len(toks)-2):
        tri = f"{toks[i]} {toks[i+1]} {toks[i+2]}"
        freq[tri] = freq.get(tri, 0) + 2.0
    ranked = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return [w for w,_ in ranked[: top_n*2]]

def _cos_sim(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0: return 0.0
    return float(np.dot(a, b) / (na * nb))

def _mmr(doc_emb, cand_embs, lambda_=0.7, k=6):
    chosen, candidates = [], list(range(len(cand_embs)))
    rel = [_cos_sim(doc_emb, e) for e in cand_embs]
    while candidates and len(chosen) < k:
        if not chosen:
            idx = int(np.argmax(rel))
            chosen.append(idx); candidates.remove(idx)
            continue
        div_scores = []
        for i in candidates:
            max_div = 0.0
            for j in chosen:
                max_div = max(max_div, _cos_sim(cand_embs[i], cand_embs[j]))
            div_scores.append((i, lambda_*rel[i] - (1-lambda_)*max_div))
        idx = max(div_scores, key=lambda x: x[1])[0]
        chosen.append(idx); candidates.remove(idx)
    return chosen

def _normalize_tag(t: str) -> str:
    t = t.lower().strip()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[^\w\s\-]", "", t)
    return t

def _nearest_in_taxonomy(tags: list[str]) -> list[str]:
    if not CONTROLLED_TAGS:
        return tags
    base = [(_normalize_tag(x), x) for x in CONTROLLED_TAGS]
    base_embs = [embed_text(b[0]) for b in base]
    out = []
    for t in tags:
        te = embed_text(t)
        if te is None:
            out.append(t); continue
        sims = [_cos_sim(np.array(te), np.array(be)) for be in base_embs]
        if sims and max(sims) >= 0.80:
            out.append(base[int(np.argmax(sims))][1])
        else:
            out.append(t)
    return out

def summarize_and_tag(text: str, top_k: int = 6) -> dict:
    summary = _summarize_chunks(text)
    c_llm = _llm_tag_candidates(text, k=20)
    c_stat = _stat_tag_candidates(text, top_n=20)
    candidates = list(dict.fromkeys([_normalize_tag(x) for x in (c_llm + c_stat)]))
    candidates = [c for c in candidates if 3 <= len(c) <= 40]
    doc_emb = embed_text(text) or embed_text(summary) or [0.0]*1536
    if not candidates:
        return {"summary": summary, "tags": []}
    cand_embs = [np.array(embed_text(c) or np.zeros(1536)) for c in candidates]
    idxs = _mmr(np.array(doc_emb), cand_embs, lambda_=0.7, k=top_k)
    tags = [candidates[i] for i in idxs]
    tags = _nearest_in_taxonomy(tags)
    return {"summary": summary, "tags": list(dict.fromkeys(tags))}
