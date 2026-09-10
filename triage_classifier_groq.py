import os
import re
import json
from groq import Groq

client = Groq(api_key=os.environ["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"])  # imposta la variabile d'ambiente, non scrivere mai la chiave qui

CODICI_VALIDI = ["ROSSO", "ARANCIONE", "GIALLO", "VERDE", "BIANCO"]
PUNTEGGIO = {"ROSSO": 5, "ARANCIONE": 4, "GIALLO": 3, "VERDE": 2, "BIANCO": 1}

EMERGENCY_KEYWORDS = [
    r"non respir", r"dolore al petto", r"dolore toracico",
    r"perdita di coscienza", r"svenut", r"emorragia", r"sangue abbondante",
    r"convulsion", r"paralisi", r"soffocament",
]


def _check_emergency_override(sintomi: str) -> bool:
    testo = sintomi.lower()
    return any(re.search(p, testo) for p in EMERGENCY_KEYWORDS)


def valuta_caso_clinico(sintomi_paziente: str) -> dict:
    """
    Prende in input la descrizione dei sintomi e restituisce
    un dizionario con codice_triage, punteggio e motivazione.
    """
    if _check_emergency_override(sintomi_paziente):
        return {
            "codice_triage": "ROSSO",
            "punteggio": PUNTEGGIO["ROSSO"],
            "motivazione": "Sintomi compatibili con emergenza immediata (rilevati da controllo di sicurezza).",
        }

    prompt = f"""Agisci come un assistente di pre-triage. Analizza i seguenti sintomi del paziente: "{sintomi_paziente}".
Restituisci un JSON puro con esattamente questa struttura:
{{"codice_triage": "ROSSO oppure ARANCIONE oppure GIALLO oppure VERDE oppure BIANCO", "motivazione": "spiegazione sintetica"}}
Usa esclusivamente uno di quei 5 valori per codice_triage, nessun altro."""

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Sei un assistente di pre-triage che restituisce solo JSON validi."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )

        risposta = json.loads(completion.choices[0].message.content)
        codice = risposta.get("codice_triage", "").upper()

        if codice not in CODICI_VALIDI:
            codice = "GIALLO"  # fallback prudenziale se il modello risponde fuori schema

        return {
            "codice_triage": codice,
            "punteggio": PUNTEGGIO[codice],
            "motivazione": risposta.get("motivazione", ""),
        }

    except Exception as e:
        return {"codice_triage": "GIALLO", "punteggio": PUNTEGGIO["GIALLO"], "motivazione": f"Errore, colore prudenziale assegnato: {e}"}


if __name__ == "__main__":
    test_cases = [
        "Dolore fortissimo al petto e fiatone",
        "Mal di testa lieve da un paio d'ore",
        "Ho bisogno solo di un certificato medico",
    ]
    for s in test_cases:
        print(s, "->", valuta_caso_clinico(s))
