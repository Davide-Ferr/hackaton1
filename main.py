from typing import Optional

import pandas as pd
from geopy.distance import geodesic
from pydantic import BaseModel

from funzioni_utilita.geolocalizzazione import geocode_address

# Caricamento CSV all'avvio.
# NB: elenco_ospedali.csv è uno snapshot statico (rilevazione del 31/07/2021
# della Regione Lazio), non un feed realmente in tempo reale: per l'hackathon
# viene usato come dato realistico di partenza, con lo schema (colonne) di
# quello che sarebbe un feed live.
df_farmacie = pd.read_csv("elenco_farmacie.csv")
df_ospedali = pd.read_csv("elenco_ospedali.csv")

# Km massimi di default che un paziente è disposto/in grado di percorrere in
# auto, in base al codice di gravità. ROSSO=0 non è un errore: un codice
# rosso non deve cercare l'ospedale "migliore", deve chiamare il 118 e
# viene comunque mostrato l'ospedale più vicino come riferimento (la stessa
# regola di fallback usata quando nessun ospedale rientra nel raggio).
KM_MASSIMI = {
    "ROSSO": 0.0,
    "GIALLO": 15.0,
    "VERDE": 30.0,
    "BIANCO": 50.0,
}
CODICI_INSTRADAMENTO_VALIDI = list(KM_MASSIMI.keys())


class UserContext(BaseModel):
    urgenza: str  # "BIANCO", "VERDE", "GIALLO" o "ROSSO"
    indirizzo: str
    range_ricerca: Optional[float] = None  # se assente, si usa KM_MASSIMI[urgenza]


def calcola_distanza_km(user_coords, target_coords) -> float:
    return geodesic(user_coords, target_coords).km


def _ospedali_ordinati_per_distanza(user_coords):
    ospedali = []
    for _, o in df_ospedali.iterrows():
        dist = calcola_distanza_km(user_coords, (o["LATITUDINE"], o["LONGITUDINE"]))
        ospedali.append((dist, o))
    ospedali.sort(key=lambda x: x[0])
    return ospedali


def _consiglia_ospedali(user_coords, urgenza: str, range_km: float, max_results: int):
    """Restituisce (lista_ospedali_consigliati, fuori_raggio).

    fuori_raggio=True significa che nessun ospedale rientrava nel raggio
    scelto/assegnato e quindi si è applicata la regola di fallback: si
    consiglia comunque l'ospedale più vicino in assoluto, indipendentemente
    dalla fila.
    """
    ospedali_con_dist = _ospedali_ordinati_per_distanza(user_coords)
    if not ospedali_con_dist:
        return [], False

    piu_vicino_dist, piu_vicino = ospedali_con_dist[0]
    entro_raggio = [(d, o) for d, o in ospedali_con_dist if d <= range_km]

    if not entro_raggio:
        attesa = int(piu_vicino[f"{urgenza}_ATT"])
        return [
            {
                "tipo": "ospedale",
                "nome": piu_vicino["ISTITUTO"],
                "comune": piu_vicino["COMUNE"],
                "lat": float(piu_vicino["LATITUDINE"]),
                "lon": float(piu_vicino["LONGITUDINE"]),
                "distanza_km": round(piu_vicino_dist, 2),
                "in_attesa_codice": attesa,
                "score": None,
                "motivo": (
                    f"Nessun ospedale entro il raggio di {range_km:.0f} km: "
                    "consigliato comunque l'ospedale più vicino in assoluto, "
                    "indipendentemente dalla fila."
                ),
            }
        ], True

    # Per i codici più gravi la distanza pesa di più (arrivare prima conta),
    # per i codici bassi pesa relativamente di più la fila (tanto non è
    # un'emergenza, meglio evitare un PS affollato anche a costo di un po'
    # di strada in più, sempre entro il raggio scelto).
    peso_distanza, peso_attesa = (3.0, 1.0) if urgenza in ("ROSSO", "GIALLO") else (1.5, 0.5)

    scored = []
    for d, o in entro_raggio:
        attesa = int(o[f"{urgenza}_ATT"])
        score = (d * peso_distanza) + (attesa * peso_attesa)
        scored.append(
            {
                "tipo": "ospedale",
                "nome": o["ISTITUTO"],
                "comune": o["COMUNE"],
                "lat": float(o["LATITUDINE"]),
                "lon": float(o["LONGITUDINE"]),
                "distanza_km": round(d, 2),
                "in_attesa_codice": attesa,
                "score": round(score, 2),
                "motivo": None,
            }
        )
    scored.sort(key=lambda x: x["score"])
    return scored[:max_results], False


def _farmacie_vicine(user_coords, range_km: float, max_results: int = 3):
    farmacie = []
    for _, f in df_farmacie.iterrows():
        dist = calcola_distanza_km(user_coords, (f["LATITUDINE"], f["LONGITUDINE"]))
        if dist <= range_km:
            farmacie.append(
                {
                    "tipo": "farmacia",
                    "nome": f["DESCRIZIONEFARMACIA"],
                    "indirizzo": f["INDIRIZZO"],
                    "lat": float(f["LATITUDINE"]),
                    "lon": float(f["LONGITUDINE"]),
                    "distanza_km": round(dist, 2),
                }
            )
    farmacie.sort(key=lambda x: x["distanza_km"])
    return farmacie[:max_results]


def get_raccomandazioni(user: UserContext, max_results: int = 5) -> dict:
    urgenza = user.urgenza.strip().upper()
    if urgenza not in CODICI_INSTRADAMENTO_VALIDI:
        raise ValueError(
            f"Codice urgenza non valido: {user.urgenza!r}. Attesi: {CODICI_INSTRADAMENTO_VALIDI}"
        )

    user_localizzazione = geocode_address(user.indirizzo)
    if user_localizzazione is None:
        raise ValueError(f"Indirizzo non trovato: {user.indirizzo!r}")
    user_coords = (user_localizzazione["lat"], user_localizzazione["lon"])

    range_km = user.range_ricerca if user.range_ricerca is not None else KM_MASSIMI[urgenza]

    ospedali_consigliati, fuori_raggio = _consiglia_ospedali(
        user_coords, urgenza, range_km, max_results
    )

    risultato = {
        "indirizzo_geocodificato": user_localizzazione["address_found"],
        "utente_lat": user_coords[0],
        "utente_lon": user_coords[1],
        "codice": urgenza,
        "range_ricerca_km": range_km,
        "ospedali_consigliati": ospedali_consigliati,
        "fuori_raggio": fuori_raggio,
    }

    if urgenza == "ROSSO":
        risultato["messaggio_prioritario"] = (
            "Chiama immediatamente il 118. Non guidare da solo: l'ospedale "
            "più vicino è mostrato solo come riferimento."
        )

    if urgenza in ("BIANCO", "VERDE"):
        risultato["farmacie_consigliate"] = _farmacie_vicine(user_coords, range_km)

    return risultato


if __name__ == "__main__":
    demo = get_raccomandazioni(
        UserContext(urgenza="ROSSO", indirizzo="Via Monginevro, Guidonia")
    )
    print(demo)
