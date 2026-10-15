"""Importa solo CESFAM de un GeoJSON a la base local; repetir no duplica registros."""
import argparse
import json
import math
from pathlib import Path
import sqlite3
from charger_data import DB_PATH

def import_cesfams(source: Path, db_path: Path = DB_PATH) -> int:
    dataset = json.loads(source.read_text(encoding='utf-8-sig'))
    records = []
    for feature in dataset['features']:
        p = feature['properties']
        if p.get('tipo') != 'Centro de Salud Familiar (CESFAM)':
            continue
        code = int(p['cod_vig'])
        lat, lon = float(p['latitud']), float(p['longitud'])
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError(f'Coordenadas inválidas para el CESFAM {code}')
        address = ' '.join(str(p.get(key) or '').strip() for key in ('via', 'direccion', 'numero')).strip()
        records.append((code, p['nombre'], address, p.get('nom_comuna') or p.get('nom_com'), p.get('nom_region') or p.get('nom_reg'), lat, lon, p.get('fono'), p.get('estado'), source.name))
    if not records:
        raise ValueError('El archivo no contiene registros clasificados como CESFAM.')
    if len({r[0] for r in records}) != len(records):
        raise ValueError('Hay códigos de CESFAM duplicados en el archivo de origen.')
    if not db_path.is_file():
        raise FileNotFoundError(f'No existe la base del chatbot: {db_path}')
    with sqlite3.connect(db_path) as db:
        db.execute('''CREATE TABLE IF NOT EXISTS cesfam (
            id INTEGER PRIMARY KEY, nombre TEXT NOT NULL, direccion TEXT,
            comuna TEXT, region TEXT, latitud REAL NOT NULL, longitud REAL NOT NULL,
            telefono TEXT, estado TEXT, archivo_fuente TEXT NOT NULL)''')
        db.executemany('''INSERT INTO cesfam
            (id,nombre,direccion,comuna,region,latitud,longitud,telefono,estado,archivo_fuente)
            VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
            nombre=excluded.nombre, direccion=excluded.direccion, comuna=excluded.comuna,
            region=excluded.region, latitud=excluded.latitud, longitud=excluded.longitud,
            telefono=excluded.telefono, estado=excluded.estado, archivo_fuente=excluded.archivo_fuente''', records)
    return len(records)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Agregar o actualizar CESFAM en la base del chatbot.')
    parser.add_argument('geojson', type=Path)
    args = parser.parse_args()
    print(f'CESFAM importados o actualizados: {import_cesfams(args.geojson)}')
