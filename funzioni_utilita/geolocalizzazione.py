from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable

def geocode_address(address: str):
    # È obbligatorio specificare un user_agent personalizzato per le policy di OpenStreetMap
    geolocator = Nominatim(user_agent="triage_app_lazio")
    
    try:
        # Aggiungiamo ", Lazio, Italia" se non presente per migliorare la precisione nel tuo contesto
        search_query = f"{address}, Lazio, Italia" if "Lazio" not in address else address
        
        location = geolocator.geocode(search_query, timeout=10)
        
        if location:
            return {
                "address_found": location.address,
                "lat": location.latitude,
                "lon": location.longitude
            }
        else:
            return None
            
    except (GeocoderTimedOut, GeocoderUnavailable) as e:
        print(f"Errore durante la geocodifica: {e}")
        return None

if __name__ == "__main__":
    # Esempio d'uso:
    indirizzo = "Piazza di Spagna 1, Roma"

    # sant andrea : 41.98276097416429, 12.470352581170618
    # ingegneria : 41.854855461179724, 12.624166049692603

    print(geocode_address(indirizzo))