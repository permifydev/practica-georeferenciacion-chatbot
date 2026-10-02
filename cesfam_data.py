"""Lectura de CESFAM y selección por distancia geográfica."""
from dataclasses import dataclass, replace
from pathlib import Path
import sqlite3
from charger_data import DB_PATH, distance_km

@dataclass(frozen=True)
class Cesfam:
    id: int
    nombre: str
    direccion: str
    comuna: str
    region: str
    latitud: float
    longitud: float
    telefono: str
    distancia_km: float = 0.0

def load_cesfams(path: Path = DB_PATH) -> list[Cesfam]:
    if not path.is_file():
        raise FileNotFoundError(f'No se encontró la base de datos: {path}')
    with sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute('SELECT id,nombre,direccion,comuna,region,latitud,longitud,telefono FROM cesfam WHERE latitud IS NOT NULL AND longitud IS NOT NULL').fetchall()
    places = []
    for row in rows:
        lat, lon = float(row['latitud']), float(row['longitud'])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        places.append(Cesfam(id=row['id'], nombre=row['nombre'],
            direccion=row['direccion'] or 'Dirección no informada',
            comuna=row['comuna'] or '', region=row['region'] or '',
            latitud=lat, longitud=lon, telefono=row['telefono'] or 'No informado'))
    return places

def nearest_cesfams(places: list[Cesfam], lat: float, lon: float, limit: int = 5) -> list[Cesfam]:
    return sorted((replace(p, distancia_km=distance_km(lat, lon, p.latitud, p.longitud)) for p in places), key=lambda p: (p.distancia_km, p.id))[:limit]
