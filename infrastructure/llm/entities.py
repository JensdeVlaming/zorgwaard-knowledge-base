from __future__ import annotations

from typing import List

from pydantic import BaseModel

from infrastructure.llm.llm_utils import llm_chat_structured


# ----------------------------------------------------------------------
# Pydantic schema's voor structured output
# ----------------------------------------------------------------------
class Entity(BaseModel):
    entity_type: str        # bv. app/proces/rol/locatie
    value: str              # originele waarde (ruw uit tekst)
    canonical_value: str    # genormaliseerd (bv. "Knox" ipv "KNOX-portal")


class EntitiesResponse(BaseModel):
    entities: List[Entity]


# ----------------------------------------------------------------------
# Entiteiten extractie
# ----------------------------------------------------------------------
def suggest_entities(text: str, max_items: int = 8) -> List[dict]:
    """
    Extraheer entiteiten uit tekst.
    Retourneert een lijst dicts met entity_type, value en canonical_value.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return []

    system_prompt = {
        "role": "system",
        "content": (
            "Je bent een extractor voor een zorgkennisbank. "
            f"Extraheer maximaal {max_items} entiteiten. "
            "Geef voor elke entiteit:\n"
            "- entity_type (bv. app, proces, rol, locatie)\n"
            "- value (exact zoals in tekst)\n"
            "- canonical_value (genormaliseerd)"
        ),
    }

    user_prompt = {"role": "user", "content": cleaned}

    parsed: EntitiesResponse | None = llm_chat_structured(
        [system_prompt, user_prompt], schema=EntitiesResponse
    )

    if not parsed:
        return []

    return [e.dict() for e in parsed.entities]
