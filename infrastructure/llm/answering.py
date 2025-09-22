from __future__ import annotations

from typing import Any, Dict, List

from infrastructure.llm.llm_utils import llm_chat


# ----------------------------------------------------------------------
# Retrieval-augmented answering
# ----------------------------------------------------------------------
def answer_from_context(question: str, matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Combineer vraag + opgehaalde documenten in een prompt en genereer antwoord.
    Houdt rekening met status (actueel, concept, vervangen) en relaties.
    """

    def format_doc(idx: int, match: Dict[str, Any]) -> str:
        metadata = match.get("metadata", {})

        # status
        status_value = str(metadata.get("status", "")).lower()
        if status_value == "archived":
            status = "VERVANGEN"
        elif status_value == "draft":
            status = "CONCEPT"
        else:
            status = "ACTUEEL"

        summary = metadata.get("summary", "")
        topic = metadata.get("topic", "Onbekend onderwerp")
        score = match.get("score")
        score_str = f"Relevantie: {score:.2f}\n" if isinstance(score, (int, float)) else ""

        # relaties kort tonen
        relations = []
        for key in ("supersedes", "superseded_by", "supports", "contradicts", "related", "duplicates"):
            refs = metadata.get(key)
            if refs:
                relations.append(f"{key}: {refs}")

        rel_str = "\n".join(relations) if relations else ""

        return (
            f"[{idx+1}] {topic} ({status})\n"
            f"{score_str}"
            f"{summary}\n"
            f"{rel_str}"
        ).strip()

    sources_block = "\n\n".join(format_doc(idx, m) for idx, m in enumerate(matches))

    system_prompt = {
        "role": "system",
        "content": (
            "Je bent een kennisbank-assistent voor zorgprofessionals. "
            "Je krijgt een vraag en een set documenten met hun status en relaties.\n\n"
            "Richtlijnen:\n"
            "- Baseer het kernantwoord op ACTUELE bronnen.\n"
            "- Gebruik SUPPORT/GERELATEERD alleen als extra context.\n"
            "- Benoem expliciet als bronnen VERVANGEN, CONCEPT of TEGENSTRIJDIG zijn.\n"
            "- Verwijs naar bronnen met hun nummer [n]."
        ),
    }

    user_prompt = {
        "role": "user",
        "content": f"Vraag: {question}\n\nBronnen:\n{sources_block}",
    }

    answer = llm_chat([system_prompt, user_prompt])

    return {
        "answer": answer,
        "trace": {
            "question": question,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "matches": matches,
        },
    }
