"""Read chargers from a local, read-only copy of the electromobility database."""

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
import sqlite3


DB_PATH = Path(__file__).parent / "cargadores.sqlite3"


@dataclass(frozen=True)
class Charger:
    id: int
    nombre: str
    direccion: str
    comuna: str
    region: str
    latitud: float
    longitud: float
    tipo_conector: str
    potencia_kw: str
    distancia_km: float = 0.0


def load_chargers(path: Path = DB_PATH) -> list[Charger]:
    if not path.is_file():
        raise FileNotFoundError(f"No se encontró la base de datos: {path}")
    # URI mode=ro prevents the chatbot from changing the copied database.
    with sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute("""
            SELECT id, nombre, direccion, comuna, region, latitud, longitud,
                   tipo_conector, potencia_kw
            FROM cargadores_cargadorelectrico
            WHERE latitud IS NOT NULL AND longitud IS NOT NULL
        """).fetchall()
    chargers = []
    for row in rows:
        lat, lon = float(row["latitud"]), float(row["longitud"])
        if not (-56 <= lat <= -17 and -76 <= lon <= -66):
            continue
        chargers.append(Charger(
            id=row["id"], nombre=row["nombre"] or "Cargador sin nombre",
            direccion=row["direccion"] or "Dirección no disponible",
            comuna=row["comuna"] or "", region=row["region"] or "",
            latitud=lat, longitud=lon,
            tipo_conector=row["tipo_conector"] or "No informado",
            potencia_kw=row["potencia_kw"] or "No informada",
        ))
    return chargers


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance (Haversine), in kilometers."""
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 6371.0088 * 2 * asin(min(1, sqrt(a)))


def nearest_chargers(chargers: list[Charger], lat: float, lon: float, limit: int = 5) -> list[Charger]:
    from dataclasses import replace
    return sorted(
        (replace(c, distancia_km=distance_km(lat, lon, c.latitud, c.longitud)) for c in chargers),
        key=lambda c: (c.distancia_km, c.id),
    )[:limit]
