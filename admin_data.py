"""Acceso SQLite para administración; no crea ni modifica las tablas originales."""
import math
import sqlite3
from contextlib import contextmanager
from charger_data import DB_PATH

TABLES = {
    'CESFAM': ('cesfam', ('nombre', 'direccion', 'comuna', 'region', 'latitud', 'longitud', 'telefono')),
    'Cargadores': ('cargadores_cargadorelectrico', ('nombre', 'direccion', 'comuna', 'region', 'latitud', 'longitud', 'tipo_conector', 'potencia_kw')),
}

@contextmanager
def connect(path=DB_PATH):
    # mode=rw evita crear por accidente una base vacía si falta el archivo.
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=rw', uri=True, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        with db:
            yield db
    finally:
        db.close()

def schema(db, kind):
    table, fields = TABLES[kind]  # nombres SQL de una lista fija, nunca del usuario
    columns = db.execute(f'PRAGMA table_info("{table}")').fetchall()
    names = {c['name'] for c in columns}
    if not {'id', *fields} <= names:
        raise ValueError(f'La tabla {table} no tiene las columnas esperadas.')
    ids = [c for c in columns if c['pk']]
    if len(ids) != 1 or ids[0]['name'] != 'id' or ids[0]['type'].upper() != 'INTEGER':
        raise ValueError('Se requiere id INTEGER PRIMARY KEY para administrar esta tabla.')
    return table, fields, columns

def list_records(kind, query='', path=DB_PATH):
    with connect(path) as db:
        table, fields, _ = schema(db, kind)
        rows = db.execute(f'SELECT id, {", ".join(fields)} FROM "{table}" ORDER BY id').fetchall()
    # Búsqueda literal: % y _ no cambian el significado de la consulta.
    term = query.strip().casefold()
    return [dict(r) for r in rows if not term or any(term in str(v).casefold() for v in r)]

def validate(kind, values):
    _, fields = TABLES[kind]
    if set(values) != set(fields):
        raise ValueError('Los campos del formulario no coinciden con la tabla.')
    clean = {k: str(v).strip() if v is not None else '' for k, v in values.items()}
    if not clean['nombre']:
        raise ValueError('El nombre es obligatorio.')
    for key, low, high in [('latitud', -90, 90), ('longitud', -180, 180)]:
        try:
            number = float(clean[key])
        except ValueError:
            raise ValueError(f'{key.capitalize()}: escribe un número válido usando punto decimal.') from None
        if not math.isfinite(number) or not low <= number <= high:
            raise ValueError(f'{key.capitalize()} debe estar entre {low} y {high}.')
        clean[key] = number
    if kind == 'Cargadores' and not (-56 <= clean['latitud'] <= -17 and -76 <= clean['longitud'] <= -66):
        raise ValueError('El buscador de cargadores requiere coordenadas dentro de su rango de Chile: latitud -56 a -17, longitud -76 a -66.')
    return clean

def save_record(kind, values, original=None, path=DB_PATH):
    clean = validate(kind, values)
    with connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        table, fields, columns = schema(db, kind)
        if original is None:
            extra = [c['name'] for c in columns if c['name'] not in {'id', *fields} and c['notnull'] and c['dflt_value'] is None]
            if extra:
                raise ValueError('La base exige campos adicionales: ' + ', '.join(extra) + '. Hay que adaptar el formulario a la base real.')
            sql = f'INSERT INTO "{table}" ({", ".join(fields)}) VALUES ({", ".join("?" for _ in fields)})'
            return db.execute(sql, [clean[f] for f in fields]).lastrowid
        _check_original(db, table, fields, original)
        db.execute(f'UPDATE "{table}" SET {", ".join(f + "=?" for f in fields)} WHERE id=?', [clean[f] for f in fields] + [original['id']])
        return original['id']

def _check_original(db, table, fields, original):
    current = db.execute(f'SELECT id, {", ".join(fields)} FROM "{table}" WHERE id=?', (original['id'],)).fetchone()
    if current is None or dict(current) != original:
        raise ValueError('El registro cambió o fue eliminado. Vuelve a seleccionarlo antes de continuar.')

def delete_record(kind, original, path=DB_PATH):
    with connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        table, fields, _ = schema(db, kind)
        _check_original(db, table, fields, original)
        db.execute(f'DELETE FROM "{table}" WHERE id=?', (original['id'],))
