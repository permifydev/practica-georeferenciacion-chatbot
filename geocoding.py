"""Resolve a user-entered Chilean address with Nominatim."""

import json
from threading import Lock
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


_lock = Lock()
_last_request = 0.0


class GeocodingError(Exception):
    pass


def geocode_address(address: str) -> tuple[float, float, str] | None:
    """Return (latitude, longitude, resolved address), or None if not found."""
    global _last_request
    query = address.strip()
    if not 4 <= len(query) <= 200:
        raise GeocodingError("Escribe una dirección de entre 4 y 200 caracteres.")
    params = urlencode({"q": query, "format": "jsonv2", "limit": 1,
                        "countrycodes": "cl", "accept-language": "es"})
    request = Request(
        f"https://nominatim.openstreetmap.org/search?{params}",
        headers={"User-Agent": "ChatbotElectromovilidadLocal/1.0 (prototipo educativo local)"},
    )
    try:
        # Nominatim public instance allows no more than one request per second.
        with _lock:
            sleep(max(0.0, 1.1 - (monotonic() - _last_request)))
            _last_request = monotonic()
            with urlopen(request, timeout=12) as response:
                results = json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise GeocodingError("No se pudo consultar la dirección. Revisa la conexión e inténtalo nuevamente.") from exc
    if not results:
        return None
    place = results[0]
    return float(place["lat"]), float(place["lon"]), place["display_name"]
