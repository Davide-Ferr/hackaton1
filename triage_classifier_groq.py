import os
import re
import json
from groq import Groq

# La chiave NON va mai scritta qui nel codice. Va impostata come variabile
# d'ambiente GROQ_API_KEY (es. in un file .env locale, mai committato — vedi
# .env.example) e letta da qui.
_client = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY non impostata. Esporta la variabile d'ambiente "
                "(es. `export GROQ_API_KEY=...` oppure un file .env) con una "
                "chiave valida generata su https://console.groq.com/keys."
            )
        _client = Groq(api_key=api_key)
    return _client


CODICI_VALIDI = ["ROSSO", "GIALLO", "VERDE", "BIANCO"]
PUNTEGGIO = {"ROSSO": 4, "GIALLO": 3, "VERDE": 2, "BIANCO": 1}

# Stesso schema a 4 codici usato dal questionario e dai dati ospedali/CSV:
# codice_triage e codice_instradamento coincidono sempre, non serve più
# nessuna normalizzazione (ARANCIONE è stato rimosso da entrambe le
# modalità di valutazione per restare sui soli 4 codici standard).

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
    Prende in input la descrizione dei sintomi e restituisce un dizionario
    con codice_triage, punteggio, motivazione e codice_instradamento (stesso
    schema a 4 codici — ROSSO/GIALLO/VERDE/BIANCO — usato per cercare gli
    ospedali; qui coincide sempre con codice_triage).
    """
    if _check_emergency_override(sintomi_paziente):
        codice = "ROSSO"
        return {
            "codice_triage": codice,
            "codice_instradamento": codice,
            "punteggio": PUNTEGGIO[codice],
            "motivazione": "Sintomi compatibili con emergenza immediata (rilevati da controllo di sicurezza).",
        }

    prompt = f"""Agisci come un assistente di pre-triage. Analizza i seguenti sintomi del paziente: "{sintomi_paziente}".
Restituisci un JSON puro con esattamente questa struttura:
{{"codice_triage": "ROSSO oppure GIALLO oppure VERDE oppure BIANCO", "motivazione": "spiegazione sintetica"}}
Usa esclusivamente uno di quei 4 valori per codice_triage, nessun altro."""

    try:
        completion = _get_client().chat.completions.create(
            model="openai/gpt-oss-120b",
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
            "codice_instradamento": codice,
            "punteggio": PUNTEGGIO[codice],
            "motivazione": risposta.get("motivazione", ""),
        }

    except Exception as e:
        codice = "GIALLO"
        return {
            "codice_triage": codice,
            "codice_instradamento": codice,
            "punteggio": PUNTEGGIO[codice],
            "motivazione": f"Errore, colore prudenziale assegnato: {e}",
        }


if __name__ == "__main__":
    test_cases = [
        "Dolore fortissimo al petto e fiatone",
        "Mal di testa lieve da un paio d'ore",
        "Ho bisogno solo di un certificato medico",
    ]
    for s in test_cases:
        print(s, "->", valuta_caso_clinico(s))
