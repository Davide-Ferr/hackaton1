"""Interfaccia unica: valutazione (AI veloce oppure questionario preciso) +
consiglio ospedale/farmacia in base a codice di gravità, geolocalizzazione e
km massimi percorribili.

Avvio: streamlit run app.py
"""

import os

import pandas as pd
import streamlit as st

try:
    from dotenv import load_dotenv

    load_dotenv()  # carica .env se presente (facoltativo, comodo in locale)
except ImportError:
    pass

import main
import triage_classifier_groq
import triage_questionario as tq

st.set_page_config(page_title="Triage & Instradamento", layout="centered")

COLORI_CODICE = {
    "ROSSO": "#d62728",
    "GIALLO": "#e0b400",
    "VERDE": "#2ca02c",
    "BIANCO": "#888888",
}


def badge_codice(codice: str):
    colore = COLORI_CODICE.get(codice, "#888888")
    st.markdown(
        f"""<div style="display:inline-block;padding:0.35em 1em;border-radius:999px;
        background:{colore};color:white;font-weight:700;font-size:1.1em;">
        Codice {codice}</div>""",
        unsafe_allow_html=True,
    )


st.title("Dove devo andare?")
st.caption(
    "Compila la valutazione (rapida con l'AI, oppure il questionario preciso) "
    "e ricevi il codice di gravità e l'ospedale/farmacia consigliati."
)

if "risultato_triage" not in st.session_state:
    st.session_state.risultato_triage = None

# --- Scelta modalità e indirizzo -------------------------------------------

MODALITA_AI = "ai"
MODALITA_QUESTIONARIO = "questionario"

modalita = st.radio(
    "Come vuoi valutare la situazione?",
    [MODALITA_AI, MODALITA_QUESTIONARIO],
    format_func=lambda v: (
        "Valutazione rapida (AI)"
        if v == MODALITA_AI
        else "Questionario preciso (più lento, più accurato)"
    ),
    help=(
        "La modalità rapida usa un'AI per stimare il codice da una breve "
        "descrizione dei sintomi: comoda quando serve fare in fretta. "
        "Il questionario è più lungo ma dà un risultato più preciso da "
        "passare al motore che cerca l'ospedale."
    ),
)

indirizzo = st.text_input(
    "Indirizzo o posizione attuale",
    placeholder="Es. Via Politecnico, 1, Roma",
)

if modalita == MODALITA_AI:
    if not os.environ.get("GROQ_API_KEY"):
        st.warning(
            "GROQ_API_KEY non è impostata: la valutazione rapida userà un "
            "codice prudenziale di fallback (GIALLO) invece dell'AI. "
            "Imposta la variabile d'ambiente per usare davvero l'AI "
            "(vedi .env.example)."
        )

    sintomi = st.text_area(
        "Descrivi brevemente i sintomi",
        placeholder="Es. Dolore fortissimo al petto e fiatone",
    )

    if st.button("Valuta con l'AI", type="primary", disabled=not sintomi.strip()):
        with st.spinner("Valutazione in corso..."):
            st.session_state.risultato_triage = triage_classifier_groq.valuta_caso_clinico(sintomi)

else:
    st.markdown("#### Fase 1 — Hai uno di questi sintomi/segni?")
    bandiere_selezionate = []
    for chiave, etichetta in tq.BANDIERE_ROSSE.items():
        if st.checkbox(etichetta, key=f"bandiera_{chiave}"):
            bandiere_selezionate.append(chiave)

    st.markdown("#### Fase 2 — Solo se non hai selezionato nulla sopra")
    st.caption(
        "Niente scale da 0 a 10: rispondi solo vero/falso a quello che il "
        "sintomo ti impedisce di fare, come farebbe un infermiere di triage."
    )

    impatto_selezionato = []
    for chiave, (etichetta, _punti) in tq.IMPATTO_FUNZIONALE.items():
        if st.checkbox(etichetta, key=f"impatto_{chiave}"):
            impatto_selezionato.append(chiave)

    col1, col2 = st.columns(2)
    with col1:
        insorgenza_improvvisa = st.checkbox("Insorgenza improvvisa (comparso in minuti/ore, non gradualmente)")
        in_peggioramento = st.checkbox("Sta peggiorando rispetto a quando è iniziato")
        eta = st.number_input("Età", min_value=0, max_value=120, value=30)
    with col2:
        sintomo_principale = st.selectbox(
            "Tipo di sintomo principale",
            options=list(tq.SINTOMI_PRINCIPALI.keys()),
            format_func=lambda k: tq.SINTOMI_PRINCIPALI[k][0],
        )
        allerta_calore_alta = st.checkbox(
            "È in corso un'allerta calore arancione/rossa nella tua zona?",
            help="Dal bollettino ondate di calore del Ministero della Salute.",
        )

    st.markdown("**Patologie pregresse** (segna solo quelle vere)")
    colf1, colf2 = st.columns(2)
    fattori_selezionati = []
    for i, (chiave, etichetta) in enumerate(tq.FATTORI_RISCHIO.items()):
        colonna = colf1 if i % 2 == 0 else colf2
        with colonna:
            if st.checkbox(etichetta, key=f"rischio_{chiave}"):
                fattori_selezionati.append(chiave)

    with st.expander("Parametri vitali misurati (opzionale, solo se li conosci)"):
        colv1, colv2, colv3 = st.columns(3)
        with colv1:
            frequenza_cardiaca = st.number_input(
                "Frequenza cardiaca (bpm)", min_value=0, max_value=300, value=0
            )
        with colv2:
            temperatura = st.number_input(
                "Temperatura (°C)", min_value=0.0, max_value=45.0, value=0.0, step=0.1
            )
        with colv3:
            saturazione = st.number_input(
                "Saturazione O2 (%)", min_value=0, max_value=100, value=0
            )

    if st.button("Calcola codice dal questionario", type="primary"):
        risposte = tq.QuestionarioRisposte(
            bandiere_rosse=bandiere_selezionate,
            impatto_funzionale=impatto_selezionato,
            insorgenza_improvvisa=insorgenza_improvvisa,
            in_peggioramento=in_peggioramento,
            sintomo_principale=sintomo_principale,
            eta=int(eta) if eta else None,
            fattori_rischio=fattori_selezionati,
            frequenza_cardiaca=int(frequenza_cardiaca) or None,
            temperatura=float(temperatura) or None,
            saturazione=int(saturazione) or None,
            allerta_calore_alta=allerta_calore_alta,
        )
        st.session_state.risultato_triage = tq.valuta_questionario(risposte)

# --- Risultato valutazione + ricerca ospedale -------------------------------

risultato = st.session_state.risultato_triage
if risultato:
    st.divider()
    st.markdown("### Risultato valutazione")
    badge_codice(risultato["codice_triage"])
    st.write(risultato["motivazione"])

    if not indirizzo.strip():
        st.info("Inserisci un indirizzo qui sopra per vedere dove recarti.")
    else:
        try:
            with st.spinner("Cerco ospedali e farmacie vicini..."):
                raccomandazioni = main.get_raccomandazioni(
                    main.UserContext(
                        urgenza=risultato["codice_instradamento"],
                        indirizzo=indirizzo,
                    )
                )
        except ValueError as e:
            st.error(str(e))
            raccomandazioni = None

        if raccomandazioni:
            st.divider()
            st.markdown("### Dove andare")
            st.caption(
                f"Posizione: {raccomandazioni['indirizzo_geocodificato']} · "
                f"raggio di ricerca: {raccomandazioni['range_ricerca_km']:.0f} km"
            )

            if raccomandazioni.get("messaggio_prioritario"):
                st.error(raccomandazioni["messaggio_prioritario"])

            if raccomandazioni["fuori_raggio"] and not raccomandazioni.get("messaggio_prioritario"):
                st.warning(
                    "Nessun ospedale entro il tuo raggio: ti consigliamo comunque "
                    "il più vicino in assoluto, indipendentemente dalla fila."
                )

            # Colori/dimensioni diversi per distinguere sulla mappa la propria
            # posizione dagli ospedali e dalle farmacie (altrimenti con
            # st.map tutti i punti sarebbero identici e la propria posizione
            # si perderebbe in mezzo agli altri, specie con molti risultati).
            punti_mappa = [
                {
                    "lat": raccomandazioni["utente_lat"],
                    "lon": raccomandazioni["utente_lon"],
                    "tipo": "La tua posizione",
                    "colore": "#1E88E5",
                    "dimensione": 120,
                }
            ]

            st.markdown("**Ospedali consigliati**")
            for o in raccomandazioni["ospedali_consigliati"]:
                punti_mappa.append(
                    {
                        "lat": o["lat"],
                        "lon": o["lon"],
                        "tipo": "Ospedale",
                        "colore": "#D62728",
                        "dimensione": 50,
                    }
                )
                riga = f"- **{o['nome']}** ({o['comune']}) — {o['distanza_km']} km, {o['in_attesa_codice']} pazienti in attesa con lo stesso codice"
                if o.get("motivo"):
                    riga += f"\n  \n  {o['motivo']}"
                st.markdown(riga)

            if raccomandazioni.get("farmacie_consigliate"):
                st.markdown("**Farmacie vicine**")
                for f in raccomandazioni["farmacie_consigliate"]:
                    punti_mappa.append(
                        {
                            "lat": f["lat"],
                            "lon": f["lon"],
                            "tipo": "Farmacia",
                            "colore": "#2CA02C",
                            "dimensione": 50,
                        }
                    )
                    st.markdown(f"- {f['nome']} — {f['indirizzo']} ({f['distanza_km']} km)")

            st.caption("Blu = la tua posizione · Rosso = ospedali · Verde = farmacie")
            df_mappa = pd.DataFrame(punti_mappa)
            st.map(df_mappa, latitude="lat", longitude="lon", color="colore", size="dimensione")
