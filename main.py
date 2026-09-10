import pandas as pd
from geopy.distance import geodesic
from pydantic import BaseModel
from funzioni_utilita.geolocalizzazione import geocode_address


# Caricamento CSV all'avvio
df_farmacie = pd.read_csv("elenco_farmacie.csv")
df_ospedali = pd.read_csv("elenco_ospedali.csv")



class UserContext(BaseModel):
    urgenza: str  # "BIANCO", "VERDE", "GIALLO", "ROSSO"
    indirizzo: str
    range_ricerca: float

def calcola_distanza_km(user_coords, target_coords):
    return geodesic(user_coords, target_coords).km

def get_raccomandazioni(user: UserContext, max_results: int = 5):
    user_localizzazione = geocode_address(user.indirizzo)
    user_coords = (user_localizzazione["lat"],user_localizzazione["lon"])
    # user_coords = (user.lat, user.lon)
    risultati = []

    # CASO 1: Urgenza Bassa (Codice Bianco / Verde)
    if user.urgenza in ["BIANCO", "VERDE"]:
        # 1. Trova le farmacie più vicine (es. entro 5 km)
        farmacie_vicine = []
        for _, f in df_farmacie.iterrows():
            dist = calcola_distanza_km(user_coords, (f['LATITUDINE'], f['LONGITUDINE']))
            if dist <= user.range_ricerca:
                farmacie_vicine.append({
                    "tipo": "farmacia",
                    "nome": f['DESCRIZIONEFARMACIA'],
                    "indirizzo": f['INDIRIZZO'],
                    "distanza_km": round(dist, 2)
                })
        farmacie_vicine = sorted(farmacie_vicine, key=lambda x: x['distanza_km'])[:3]
        risultati.extend(farmacie_vicine)

        # 2. Aggiungi ospedali con poca occupazione/attesa per codici bassi
        for _, o in df_ospedali.iterrows():
            dist = calcola_distanza_km(user_coords, (o['LATITUDINE'], o['LONGITUDINE']))
            in_attesa = o['BIANCO_ATT'] + o['VERDE_ATT']
            
            # Formula di score: dà peso sia alla distanza che al carico di attesa
            score = (dist * 1.5) + (in_attesa * 0.5)
            
            risultati.append({
                "tipo": "ospedale",
                "nome": o['ISTITUTO'],
                "distanza_km": round(dist, 2),
                "in_attesa_codice": in_attesa,
                "score": score
            })

    # CASO 2: Urgenza Media/Alta (Codice Giallo / Rosso)
    else:
        for _, o in df_ospedali.iterrows():
            dist = calcola_distanza_km(user_coords, (o['LATITUDINE'], o['LONGITUDINE']))
            
            # Per codici alti la distanza ha peso primario, ma l'occupazione influisce sui tempi di presa in carico
            attesa_specifica = o[f'{user.urgenza.upper()}_ATT']
            score = (dist * 3.0) + (attesa_specifica * 1.0)

            risultati.append({
                "tipo": "ospedale",
                "nome": o['ISTITUTO'],
                "distanza_km": round(dist, 2),
                "in_attesa_codice": attesa_specifica,
                "score": score
            })

    # Ordina per score crescente e restituisce i primi N risultati
    ospedali_filtrati = [r for r in risultati if r['tipo'] == 'ospedale']
    ospedali_ordinati = sorted(ospedali_filtrati, key=lambda x: x['score'])[:max_results]
    
    if user.urgenza in ["BIANCO", "VERDE"]:
        return {
            "farmacie_consigliate": farmacie_vicine,
            "ospedali_consigliati": ospedali_ordinati
        }
    
    return {"ospedali_consigliati": ospedali_ordinati}

# print(get_raccomandazioni(UserContext(urgenza="giallo",)))
# print(get_raccomandazioni(UserContext(urgenza="ROSSO",lat=41.98276097416429,lon=12.470352581170618,)))
print(get_raccomandazioni(UserContext(urgenza="ROSSO",indirizzo="Via Monginevro,Guidonia",range_ricerca=20.0)))
# print(geocode_address("Via monginevro, Guidonia")["lat"])