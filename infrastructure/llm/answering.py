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

    id_lookup = {match.get("id"): idx + 1 for idx, match in enumerate(matches)}

    def format_doc(idx: int, match: Dict[str, Any]) -> str:
        metadata = match.get("metadata", {})

        summary = metadata.get("summary", "")
        topic = metadata.get("topic", "Onbekend onderwerp")
        status = metadata.get("status")
        created_at = metadata.get("created_at")

        relation_lines: List[str] = []
        for relation in metadata.get("relations", []) or []:
            descriptor = relation.get("descriptor") or relation.get("relation_type")
            other_id = relation.get("other_id")

            if other_id and other_id in id_lookup:
                reference = f"[{id_lookup[other_id]}]"
                relation_lines.append(f"{descriptor} {reference}")

        header = f"[{idx+1}] {topic}"

        lines = [header]
        if created_at:
            lines.append(f"Datum: {created_at}")
        if summary:
            lines.append(summary)
        if relation_lines:
            lines.append("\n".join(relation_lines))

        return "\n".join(lines).strip()

    sources_block = "\n\n".join(format_doc(idx, m) for idx, m in enumerate(matches))
    system_prompt = {
        "role": "system",
        "content": (
            "Je bent een Nederlandstalige kennisbank-assistent voor zorgprofessionals.\n"
            "Je beantwoordt vragen uitsluitend op basis van de meegeleverde bronnen en hun metadata/relaties.\n"
            "Gebruik geen externe kennis.\n"
            "\n"
            "Antwoord-volgorde\n"
            "Begin altijd met het daadwerkelijke antwoord in de tegenwoordige tijd, vervolgens pas context of historie. "
            "Formuleer de eerste zin als huidige stand van zaken + korte onderbouwing met citatie. "
            "Voorbeeld: 'Beheer ligt bij persoon Y [2]; voorheen was dit persoon X, maar Y vervangt X volgens [1] [2].'\n"
            "\n"
            "Doelstelling\n"
            "Lever een kort, feitelijk antwoord dat volledig herleidbaar is naar de meegegeven bronnen.\n"
            "\n"
            "Citaties\n"
            "Plaats bronverwijzingen in het formaat [n] direct na elke niet-triviale bewering; scheid meerdere verwijzingen met spaties.\n"
            "\n"
            "Relatiemodel\n"
            "Gebruik de termen: ondersteunt, spreekt tegen, vult aan, verduidelijkt, vervangt, wordt vervangen door.\n"
            "Verwerk in lopende tekst welke bron welke andere bron ondersteunt, tegenspreekt of vervangt, inclusief citaties.\n"
            "\n"
            "Vervanging en veroudering\n"
            "Bij expliciete vervanging gebruik je de vervangende bron voor de feiten en noem je dat deze de oudere bron vervangt.\n"
            "Bij deelvervanging benoem je de scope.\n"
            "Negeer ingetrokken of verlopen bronnen en vermeld dit beknopt.\n"
            "Bij conflicten zonder expliciete relatie hanteer je de prioriteit: actuele geldigheid > publicatiedatum > versie > formele autoriteit/uitgever > relevantiescore.\n"
            "Als het onbeslisbaar blijft, markeer dit en benoem welke aanvullende informatie nodig is.\n"
            "Noem expliciet datums en versies bij updates.\n"
            "\n"
            "Gedragsregels\n"
            "Baseer je uitsluitend op de bronnen; verzin niets.\n"
            "Beperk je tot informatie die de vraag direct beantwoordt.\n"
            "Als iets ontbreekt of onduidelijk is, zeg dat expliciet en specificeer wat nodig is (bijv. nieuwere versie, ontbrekende bijlage, duidelijkere scope).\n"
            "Gebruik neutrale, professionele formuleringen; geen advies buiten de broninhoud.\n"
            "\n"
            "Outputstijl\n"
            "Schrijf uitsluitend in alinea’s, zonder genummerde of bullet-opsommingen.\n"
            "Combineer antwoord, relatie-duiding en eventuele onzekerheden in samenhangende alinea’s met citaties; het hoeft geen enkele lange doorlopende tekst te zijn.\n"
            "\n"
            "Omgaan met hiaten\n"
            "Als informatie ontbreekt of onduidelijk is, zeg dat expliciet en specificeer wat nog nodig is (bijv. nieuwere versie, ontbrekende bijlage, duidelijke scope).\n"
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
