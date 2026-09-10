"""Motore di triage "modalità precisa": un questionario a punteggio invece
della valutazione AI veloce.

Impostazione: niente scale soggettive ("quanto è intenso il dolore da 0 a
10?") che lasciano spazio a "presentimento" dell'utente. Ogni domanda è una
domanda oggettiva/comportamentale a cui si risponde vero/falso, come farebbe
un infermiere di triage (es. "riesci a parlare in frasi complete?" invece di
"quanto fa male?"). La gravità emerge dalla combinazione delle risposte, non
da un numero scelto a sensazione dal paziente.

Restituisce lo stesso formato di
triage_classifier_groq.valuta_caso_clinico, così il resto del programma
(main.py / l'interfaccia) può trattare le due modalità in modo intercambiabile.
"""

from typing import List, Optional

from pydantic import BaseModel, Field

CODICI_VALIDI = ["ROSSO", "GIALLO", "VERDE", "BIANCO"]
PUNTEGGIO = {"ROSSO": 4, "GIALLO": 3, "VERDE": 2, "BIANCO": 1}

# --- Fase 1: bandiere rosse -------------------------------------------------
# Domande vero/falso. Se anche una sola è vera, si assegna direttamente
# ROSSO e si salta il resto: sono segni che da soli bastano a definire
# un'emergenza, senza bisogno di combinarli con altro.
BANDIERE_ROSSE = {
    "perdita_coscienza": "Perdita di coscienza in corso o recente",
    "difficolta_respiratoria_grave": "Difficoltà a respirare grave / fame d'aria",
    "dolore_toracico_oppressivo": "Dolore al petto oppressivo, con sudorazione o irradiato a braccio/mascella/schiena",
    "sanguinamento_abbondante": "Sanguinamento abbondante che non si arresta",
    "segni_ictus": "Segni di ictus: viso asimmetrico, difficoltà a parlare, debolezza improvvisa a un lato",
    "trauma_cranico_con_confusione": "Trauma cranico con confusione, vomito ripetuto o perdita di coscienza",
    "convulsioni_in_corso": "Convulsioni in corso",
    "reazione_allergica_severa": "Reazione allergica severa (gonfiore a gola/lingua, difficoltà respiratoria)",
    "colpo_di_calore_grave": "Colpo di calore con alterazione della coscienza o temperatura corporea >40°C",
}

# --- Fase 2: impatto funzionale (sostituisce la scala di intensità) --------
# Invece di chiedere "quanto fa male da 0 a 10" (soggettivo), si chiedono
# fatti osservabili sul corpo: quello che il sintomo IMPEDISCE di fare. È
# la stessa logica usata nei protocolli di triage reali (i "discriminatori")
# al posto dell'autovalutazione del dolore.
IMPATTO_FUNZIONALE = {
    "non_parla_frasi_complete": ("Il sintomo ti impedisce di parlare in frasi complete senza fermarti", 5),
    "non_cammina_da_solo": ("Il sintomo ti impedisce di camminare o stare in piedi da solo", 4),
    "non_attivita_quotidiane": ("Il sintomo ti impedisce di svolgere le normali attività (lavoro, studio, faccende)", 2),
    "disturba_sonno": ("Il sintomo ti ha svegliato di notte o ti impedisce di dormire", 1),
}

# Categorie neutre: descrivono SOLO il tipo di sintomo, senza aggettivi di
# gravità ("forte", "lieve") che richiederebbero un giudizio soggettivo.
SINTOMI_PRINCIPALI = {
    "febbre": ("Febbre", 1),
    "vomito_o_diarrea": ("Vomito o diarrea", 1),
    "dolore_addominale": ("Dolore addominale", 2),
    "difficolta_respiratoria": ("Difficoltà respiratoria (anche lieve/intermittente)", 3),
    "trauma_arto": ("Trauma con impotenza funzionale (non riesci a muovere/caricare l'arto)", 2),
    "sintomi_da_calore": ("Sintomi da calore (crampi, sudorazione profusa, debolezza)", 2),
    "mal_di_testa": ("Mal di testa", 1),
    "vertigini": ("Vertigini o capogiri", 2),
    "dolore_articolare_muscolare": ("Dolore articolare o muscolare (non da trauma acuto)", 1),
    "ferita_da_medicare": ("Ferita/taglio che potrebbe necessitare punti o medicazione", 2),
    "eruzione_cutanea": ("Eruzione cutanea o reazione allergica lieve (senza difficoltà respiratoria)", 2),
    "mal_di_gola": ("Mal di gola", 1),
}

FATTORI_RISCHIO = {
    "cardiopatia": "Hai una malattia cardiaca diagnosticata",
    "diabete": "Hai il diabete",
    "immunodepressione": "Sei immunodepresso/a (es. terapie che abbassano le difese immunitarie)",
    "gravidanza": "Sei in gravidanza",
}


class QuestionarioRisposte(BaseModel):
    # Fase 1
    bandiere_rosse: List[str] = Field(default_factory=list)  # chiavi di BANDIERE_ROSSE segnate "sì"

    # Fase 2 (usate solo se nessuna bandiera rossa è segnata) — tutto
    # vero/falso o dati oggettivi (età, parametri misurati), niente scale.
    impatto_funzionale: List[str] = Field(default_factory=list)  # chiavi di IMPATTO_FUNZIONALE segnate "sì"
    insorgenza_improvvisa: bool = False  # comparso in minuti/ore, non gradualmente
    in_peggioramento: bool = False  # sta peggiorando rispetto a quando è iniziato
    sintomo_principale: str = "febbre"  # chiave di SINTOMI_PRINCIPALI
    eta: Optional[int] = None
    fattori_rischio: List[str] = Field(default_factory=list)  # chiavi di FATTORI_RISCHIO segnate "sì"
    frequenza_cardiaca: Optional[int] = None  # bpm, solo se misurata
    temperatura: Optional[float] = None  # °C, solo se misurata
    saturazione: Optional[int] = None  # %, solo se misurata

    # Modificatore ondata di calore (opzionale, da bollettino Ministero Salute)
    allerta_calore_alta: bool = False  # livello bollettino arancione o rosso nella zona


def _punti_eta(eta: Optional[int]) -> int:
    if eta is None:
        return 0
    if eta < 1 or eta > 75:
        return 3
    if eta >= 65:
        return 2
    return 0


def _punti_vitali(risposte: QuestionarioRisposte) -> int:
    punti = 0
    if risposte.frequenza_cardiaca is not None and (
        risposte.frequenza_cardiaca > 120 or risposte.frequenza_cardiaca < 50
    ):
        punti += 3
    if risposte.temperatura is not None and risposte.temperatura > 39.5:
        punti += 2
    if risposte.saturazione is not None and risposte.saturazione < 94:
        punti += 4
    return punti


def _codice_da_punteggio(punti: int) -> str:
    if punti >= 13:
        return "ROSSO"
    if punti >= 8:
        return "GIALLO"
    if punti >= 4:
        return "VERDE"
    return "BIANCO"


def valuta_questionario(risposte: QuestionarioRisposte) -> dict:
    bandiere_attive = [b for b in risposte.bandiere_rosse if b in BANDIERE_ROSSE]
    if bandiere_attive:
        motivi = "; ".join(BANDIERE_ROSSE[b] for b in bandiere_attive)
        codice = "ROSSO"
        return {
            "codice_triage": codice,
            "codice_instradamento": codice,
            "punteggio": PUNTEGGIO[codice],
            "punteggio_dettaglio": None,
            "motivazione": f"Bandiera rossa rilevata: {motivi}.",
        }

    punti = 0

    punti_impatto = sum(
        IMPATTO_FUNZIONALE[k][1] for k in risposte.impatto_funzionale if k in IMPATTO_FUNZIONALE
    )
    punti += punti_impatto

    punti += 2 if risposte.insorgenza_improvvisa else 0
    punti += 2 if risposte.in_peggioramento else 0

    _, punti_sintomo = SINTOMI_PRINCIPALI.get(risposte.sintomo_principale, ("Non specificato", 1))
    punti += punti_sintomo

    punti += _punti_eta(risposte.eta)

    punti_rischio = sum(1 for r in risposte.fattori_rischio if r in FATTORI_RISCHIO)
    punti += punti_rischio

    punti += _punti_vitali(risposte)

    modificatore_calore = 0
    if risposte.allerta_calore_alta and (
        risposte.sintomo_principale == "sintomi_da_calore" or risposte.fattori_rischio
    ):
        modificatore_calore = 3
        punti += modificatore_calore

    codice = _codice_da_punteggio(punti)

    return {
        "codice_triage": codice,
        "codice_instradamento": codice,
        "punteggio": PUNTEGGIO[codice],
        "punteggio_dettaglio": {
            "totale": punti,
            "impatto_funzionale": punti_impatto,
            "fattori_rischio": punti_rischio,
            "modificatore_calore": modificatore_calore,
        },
        "motivazione": f"Punteggio questionario: {punti} → codice {codice}.",
    }


if __name__ == "__main__":
    casi = {
        "raffreddore lieve": QuestionarioRisposte(
            sintomo_principale="febbre",
            eta=30,
        ),
        "dolore addominale con impatto forte, anziano a rischio": QuestionarioRisposte(
            impatto_funzionale=["non_cammina_da_solo", "non_attivita_quotidiane"],
            insorgenza_improvvisa=True,
            sintomo_principale="dolore_addominale",
            eta=70,
            fattori_rischio=["cardiopatia"],
        ),
        "non riesce a parlare in frasi complete": QuestionarioRisposte(
            impatto_funzionale=["non_parla_frasi_complete", "non_cammina_da_solo"],
            insorgenza_improvvisa=True,
            in_peggioramento=True,
            sintomo_principale="difficolta_respiratoria",
            eta=45,
        ),
    }
    for nome, risposte in casi.items():
        print(nome, "->", valuta_questionario(risposte))
