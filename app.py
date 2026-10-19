"""Chatbot local. Código único; datos y hashes en SQLite. Gestión de usuarios por CMD."""
#*************************************
# CHARGER_DATA
#************************************

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
import sqlite3
DB_PATH = Path(__file__).parent / 'cesfam_y_cargadores.sqlite3'

#***************************************************************************************************************
# Define los datos que representa un cargador: nombre, dirección, coordenadas, conector, potencia y distancia    
#***************************************************************************************************************

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

#***************************************************************************************************************
# Lee los cargadores de SQLite, descarta coordenadas fuera del rango definido y devuelve una lista de objetos Charger   
#***************************************************************************************************************

def load_chargers(path: Path=DB_PATH) -> list[Charger]:
    if not path.is_file():
        raise FileNotFoundError(f'No se encontró la base de datos: {path}')
    with sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute('\n            SELECT id, nombre, direccion, comuna, region, latitud, longitud,\n                   tipo_conector, potencia_kw\n            FROM cargadores_cargadorelectrico\n            WHERE latitud IS NOT NULL AND longitud IS NOT NULL\n        ').fetchall()
    chargers = []
    for row in rows:
        lat, lon = (float(row['latitud']), float(row['longitud']))
        if not (-56 <= lat <= -17 and -76 <= lon <= -66):
            continue
        chargers.append(Charger(id=row['id'], nombre=row['nombre'] or 'Cargador sin nombre', direccion=row['direccion'] or 'Dirección no disponible', comuna=row['comuna'] or '', region=row['region'] or '', latitud=lat, longitud=lon, tipo_conector=row['tipo_conector'] or 'No informado', potencia_kw=row['potencia_kw'] or 'No informada'))
    return chargers

#***************************************************************************************************************
# Calcula la distancia en línea recta entre dos coordenadas mediante Haversine. Devuelve kilómetros  
#***************************************************************************************************************

def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance (Haversine), in kilometers."""
    dlat, dlon = (radians(lat2 - lat1), radians(lon2 - lon1))
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 6371.0088 * 2 * asin(min(1, sqrt(a)))

#***************************************************************************************************************
# Calcula las distancias, ordena los cargadores del más cercano al más lejano y devuelve la cantidad solicitada.
#***************************************************************************************************************

def nearest_chargers(chargers: list[Charger], lat: float, lon: float, limit: int=5) -> list[Charger]:
    from dataclasses import replace
    return sorted((replace(c, distancia_km=distance_km(lat, lon, c.latitud, c.longitud)) for c in chargers), key=lambda c: (c.distancia_km, c.id))[:limit]

#***********************
# CESFAM_DATA           *******************************
#**********************

from dataclasses import dataclass, replace
from pathlib import Path
import sqlite3

@dataclass(frozen=True)

#***************************************************************************************************************
# Define los datos de un CESFAM, incluyendo teléfono y distancia.
#***************************************************************************************************************

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

#***************************************************************************************************************
# Consulta la tabla cesfam, valida las coordenadas y devuelve los establecimientos.
#***************************************************************************************************************

def load_cesfams(path: Path=DB_PATH) -> list[Cesfam]:
    if not path.is_file():
        raise FileNotFoundError(f'No se encontró la base de datos: {path}')
    with sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute('SELECT id,nombre,direccion,comuna,region,latitud,longitud,telefono FROM cesfam WHERE latitud IS NOT NULL AND longitud IS NOT NULL').fetchall()
    places = []
    for row in rows:
        lat, lon = (float(row['latitud']), float(row['longitud']))
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        places.append(Cesfam(id=row['id'], nombre=row['nombre'], direccion=row['direccion'] or 'Dirección no informada', comuna=row['comuna'] or '', region=row['region'] or '', latitud=lat, longitud=lon, telefono=row['telefono'] or 'No informado'))
    return places

#***************************************************************************************************************
# Utiliza distance_km() para ordenar los CESFAM por cercanía y seleccionar los primeros resultados.
#***************************************************************************************************************

def nearest_cesfams(places: list[Cesfam], lat: float, lon: float, limit: int=5) -> list[Cesfam]:
    return sorted((replace(p, distancia_km=distance_km(lat, lon, p.latitud, p.longitud)) for p in places), key=lambda p: (p.distancia_km, p.id))[:limit]

#************************
# GEOCODING              **********************************************
# Este bloque convierte una dirección escrita en coordenadas.
#************************

import json
from threading import Lock
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
_lock = Lock()
_last_request = 0.0

#***************************************************************************************************************
# Define un tipo de error propio para los problemas al consultar una dirección
#***********************************************************************************************************

class GeocodingError(Exception):
    pass

#***************************************************************************************************************
# Envía la dirección a Nominatim y devuelve latitud, longitud y el nombre de la ubicación encontrada.
#***********************************************************************************************************

def geocode_address(address: str) -> tuple[float, float, str] | None:
    """Return (latitude, longitude, resolved address), or None if not found."""
    global _last_request
    query = address.strip()
    if not 4 <= len(query) <= 200:
        raise GeocodingError('Escribe una dirección de entre 4 y 200 caracteres.')
    params = urlencode({'q': query, 'format': 'jsonv2', 'limit': 1, 'countrycodes': 'cl', 'accept-language': 'es'})
    request = Request(f'https://nominatim.openstreetmap.org/search?{params}', headers={'User-Agent': 'ChatbotElectromovilidadLocal/1.0 (prototipo educativo local)'})
    try:
        with _lock:
            sleep(max(0.0, 1.1 - (monotonic() - _last_request)))
            _last_request = monotonic()
            with urlopen(request, timeout=12) as response:
                results = json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise GeocodingError('No se pudo consultar la dirección. Revisa la conexión e inténtalo nuevamente.') from exc
    if not results:
        return None
    place = results[0]
    return (float(place['lat']), float(place['lon']), place['display_name'])

#********************************************
# ADMIN_AUTH                               ***********************************************
#********************************************

import argparse
import getpass
import hashlib
import hmac
import secrets
import sqlite3
AUTH_PATH = DB_PATH

#***************************************************************************************************************
#Calcula el hash scrypt utilizando la contraseña y su salt.
#***********************************************************************************************************

def password_hash(password, salt):
    return hashlib.scrypt(password.encode('utf-8'), salt=salt, n=16384, r=8, p=1, dklen=32)

#***************************************************************************************************************
# Comprueba usuario y contraseña; devuelve True o False.
#*********************************************************************************************************** 

def authenticate(username, password, path=AUTH_PATH):
    if not path.is_file():
        return False
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as db:
        row = db.execute('SELECT salt, password_hash FROM administradores WHERE username=?', (username.strip(),)).fetchone()
    salt, expected = row if row else (b'\x00' * 16, b'\x00' * 32)
    actual = password_hash(password, salt)
    return row is not None and hmac.compare_digest(actual, expected)


#***************************************************************************************************************
# Crea un administrador o cambia su contraseña si recibe reset=True. Genera un salt y hash nuevos.
#*********************************************************************************************************** 

def create_admin(username, password, path=AUTH_PATH, reset=False):
    username = username.strip()
    if not username or len(username) > 100:
        raise ValueError('El usuario debe tener entre 1 y 100 caracteres.')
    if len(password) < 12:
        raise ValueError('Usa una contraseña de al menos 12 caracteres.')
    salt = secrets.token_bytes(16)
    digest = password_hash(password, salt)
    with sqlite3.connect(path.resolve().as_uri() + '?mode=rw', uri=True) as db:
        db.execute('CREATE TABLE IF NOT EXISTS administradores (username TEXT PRIMARY KEY, salt BLOB NOT NULL, password_hash BLOB NOT NULL)')
        if reset:
            cursor = db.execute('UPDATE administradores SET salt=?, password_hash=? WHERE username=?', (salt, digest, username))
            if cursor.rowcount != 1:
                raise ValueError('No existe ese usuario.')
        else:
            db.execute('INSERT INTO administradores VALUES (?, ?, ?)', (username, salt, digest))

#********************************************
# ADMIN_DATA                                   ********************************
#*********************************************


import math
import sqlite3
from contextlib import contextmanager
TABLES = {'CESFAM': ('cesfam', ('nombre', 'direccion', 'comuna', 'region', 'latitud', 'longitud', 'telefono')), 'Cargadores': ('cargadores_cargadorelectrico', ('nombre', 'direccion', 'comuna', 'region', 'latitud', 'longitud', 'tipo_conector', 'potencia_kw'))}

@contextmanager

#***************************************************************************************************************
# Abre la conexión para modificar datos, confirma los cambios si todo
#  termina bien, los revierte si ocurre un error y cierra la conexión.
#*********************************************************************************************************** 

def connect(path=DB_PATH):
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=rw', uri=True, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        with db:
            yield db
    finally:
        db.close()

#***************************************************************************************************************
# Comprueba que la tabla tenga los campos y la clave primaria esperados
#***********************************************************************************************************         

def schema(db, kind):
    table, fields = TABLES[kind]
    columns = db.execute(f'PRAGMA table_info("{table}")').fetchall()
    names = {c['name'] for c in columns}
    if not {'id', *fields} <= names:
        raise ValueError(f'La tabla {table} no tiene las columnas esperadas.')
    ids = [c for c in columns if c['pk']]
    if len(ids) != 1 or ids[0]['name'] != 'id' or ids[0]['type'].upper() != 'INTEGER':
        raise ValueError('Se requiere id INTEGER PRIMARY KEY para administrar esta tabla.')
    return (table, fields, columns)

#***************************************************************************************************************
# Lee los registros y permite filtrarlos por un texto de búsqueda.
#*********************************************************************************************************** 

def list_records(kind, query='', path=DB_PATH):
    with connect(path) as db:
        table, fields, _ = schema(db, kind)
        rows = db.execute(f'''SELECT id, {', '.join(fields)} FROM "{table}" ORDER BY id''').fetchall()
    term = query.strip().casefold()
    return [dict(r) for r in rows if not term or any((term in str(v).casefold() for v in r))]

#***************************************************************************************************************
# Limpia los valores y revisa campos obligatorios y coordenadas antes de guardarlos..
#*********************************************************************************************************** 

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
    if kind == 'Cargadores' and (not (-56 <= clean['latitud'] <= -17 and -76 <= clean['longitud'] <= -66)):
        raise ValueError('El buscador de cargadores requiere coordenadas dentro de su rango de Chile: latitud -56 a -17, longitud -76 a -66.')
    return clean

#***************************************************************************************************************
# Agrega un registro nuevo o actualiza uno existente.
#*********************************************************************************************************** 

def save_record(kind, values, original=None, path=DB_PATH):
    clean = validate(kind, values)
    with connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        table, fields, columns = schema(db, kind)
        if original is None:
            if kind == 'CESFAM' and any((c['name'] == 'archivo_fuente' for c in columns)):
                fields = (*fields, 'archivo_fuente')
                clean['archivo_fuente'] = 'Administración local'
            extra = [c['name'] for c in columns if c['name'] not in {'id', *fields} and c['notnull'] and (c['dflt_value'] is None)]
            if extra:
                raise ValueError('La base exige campos adicionales: ' + ', '.join(extra) + '. Hay que adaptar el formulario a la base real.')
            sql = f'''INSERT INTO "{table}" ({', '.join(fields)}) VALUES ({', '.join(('?' for _ in fields))})'''
            return db.execute(sql, [clean[f] for f in fields]).lastrowid
        _check_original(db, table, fields, original)
        db.execute(f'''UPDATE "{table}" SET {', '.join((f + '=?' for f in fields))} WHERE id=?''', [clean[f] for f in fields] + [original['id']])
        return original['id']

#***************************************************************************************************************
# Comprueba que el registro no haya cambiado desde que lo seleccionaste.
#*********************************************************************************************************** 

def _check_original(db, table, fields, original):
    current = db.execute(f'''SELECT id, {', '.join(fields)} FROM "{table}" WHERE id=?''', (original['id'],)).fetchone()
    if current is None or dict(current) != original:
        raise ValueError('El registro cambió o fue eliminado. Vuelve a seleccionarlo antes de continuar.')

#***************************************************************************************************************
# Elimina el registro seleccionado después de comprobar su versión original.
#***********************************************************************************************************     

def delete_record(kind, original, path=DB_PATH):
    with connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        table, fields, _ = schema(db, kind)
        _check_original(db, table, fields, original)
        db.execute(f'DELETE FROM "{table}" WHERE id=?', (original['id'],))

#********************************************************************
# IMPORTAR_CESFAM                                                      *********************************
#**********************************************************************

import argparse
import json
import math
from pathlib import Path
import sqlite3

#***************************************************************************************************************
# Lee un GeoJSON e incorpora o actualiza los registros clasificados como CESFAM.

# Extrae nombre, dirección, coordenadas, teléfono y otros datos.
# Comprueba las coordenadas y los códigos duplicados.
# Agrega los registros nuevos.
# Actualiza los que ya existen utilizando su identificador.
# Devuelve la cantidad procesada.

#*********************************************************************************************************** 

def import_cesfams(source: Path, db_path: Path=DB_PATH) -> int:
    dataset = json.loads(source.read_text(encoding='utf-8-sig'))
    records = []
    for feature in dataset['features']:
        p = feature['properties']
        if p.get('tipo') != 'Centro de Salud Familiar (CESFAM)':
            continue
        code = int(p['cod_vig'])
        lat, lon = (float(p['latitud']), float(p['longitud']))
        if not (math.isfinite(lat) and math.isfinite(lon) and (-90 <= lat <= 90) and (-180 <= lon <= 180)):
            raise ValueError(f'Coordenadas inválidas para el CESFAM {code}')
        address = ' '.join((str(p.get(key) or '').strip() for key in ('via', 'direccion', 'numero'))).strip()
        records.append((code, p['nombre'], address, p.get('nom_comuna') or p.get('nom_com'), p.get('nom_region') or p.get('nom_reg'), lat, lon, p.get('fono'), p.get('estado'), source.name))
    if not records:
        raise ValueError('El archivo no contiene registros clasificados como CESFAM.')
    if len({r[0] for r in records}) != len(records):
        raise ValueError('Hay códigos de CESFAM duplicados en el archivo de origen.')
    if not db_path.is_file():
        raise FileNotFoundError(f'No existe la base del chatbot: {db_path}')
    with sqlite3.connect(db_path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS cesfam (\n            id INTEGER PRIMARY KEY, nombre TEXT NOT NULL, direccion TEXT,\n            comuna TEXT, region TEXT, latitud REAL NOT NULL, longitud REAL NOT NULL,\n            telefono TEXT, estado TEXT, archivo_fuente TEXT NOT NULL)')
        db.executemany('INSERT INTO cesfam\n            (id,nombre,direccion,comuna,region,latitud,longitud,telefono,estado,archivo_fuente)\n            VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET\n            nombre=excluded.nombre, direccion=excluded.direccion, comuna=excluded.comuna,\n            region=excluded.region, latitud=excluded.latitud, longitud=excluded.longitud,\n            telefono=excluded.telefono, estado=excluded.estado, archivo_fuente=excluded.archivo_fuente', records)
    return len(records)

#********************************************
# ADMIN_UI                                   *******************************************
#********************************************

import sqlite3
import time
import streamlit as st
LABELS = {'nombre': 'Nombre', 'direccion': 'Dirección', 'comuna': 'Comuna', 'region': 'Región', 'latitud': 'Latitud', 'longitud': 'Longitud', 'telefono': 'Teléfono', 'tipo_conector': 'Tipo de conector', 'potencia_kw': 'Potencia (kW)'}

#***************************************************************************************************************
# Limpia los datos de la sesión administrativa y vuelve al inicio. Conserva los contadores de intentos fallidos.
#***********************************************************************************************************     

def logout():
    for key in list(st.session_state):
        if key.startswith('admin_') and key not in ('admin_attempts', 'admin_block_until'):
            del st.session_state[key]
    st.session_state.app_screen = 'home'

#***************************************************************************************************************
# Revisa que exista una sesión, que las credenciales sigan vigentes y que no hayan pasado 30 minutos de inactividad
#***********************************************************************************************************     

def session_is_active():
    """Comprueba vencimiento antes de acceder a cualquier pantalla privada."""
    if not st.session_state.get('admin_user'):
        return False
    try:
        current = credential_version(st.session_state.admin_user)
    except (sqlite3.Error, OSError):
        current = None
    if not current or current != st.session_state.get('admin_credential_version'):
        logout()
        st.session_state.app_screen = 'login'
        st.session_state.login_notice = 'Las credenciales cambiaron o el usuario fue eliminado. Inicia sesión nuevamente.'
        return False
    if time.time() - st.session_state.get('admin_last_activity', 0) > 1800:
        logout()
        st.session_state.app_screen = 'login'
        st.session_state.login_notice = 'La sesión expiró por inactividad. Inicia sesión nuevamente.'
        return False
    return True

#***************************************************************************************************************
# Selecciona la pantalla de búsqueda pública.
#***********************************************************************************************************     

def open_public_search():
    st.session_state.app_screen = 'public'

#***************************************************************************************************************
# Selecciona la pantalla principal.
#***********************************************************************************************************     

def go_home():
    st.session_state.app_screen = 'home'

#***************************************************************************************************************
# Cierra la sesión administrativa anterior y selecciona el login.
#***********************************************************************************************************         

def request_admin_login():
    logout()
    st.session_state.app_screen = 'login'

#***************************************************************************************************************
# Muestra la pantalla principal con los botones de búsqueda y administración.
#***********************************************************************************************************         

def render_home():
    """Inicio público con dos botones, sin formulario de contraseña."""
    _, center, _ = st.columns([1, 2, 1])
    with center:
        st.title('📍 Servicios cercanos')
        st.caption('Encuentra Cesfam y Cargadores eléctricos cerca de tu dirección.')
        with st.container(border=True):
            st.subheader('¿Qué quieres hacer?')
            st.button('📍CESFAM y CARGADORES', type='primary', on_click=open_public_search, use_container_width=True)
            st.caption('Consulta ubicaciones y distancias sin iniciar sesión.')
            st.button('🔒 Administración', on_click=request_admin_login, use_container_width=True)
            st.caption('Acceso con usuario y contraseña para gestionar los registros.')

#***************************************************************************************************************
# Muestra el formulario, comprueba las credenciales e inicia la sesión.
#***********************************************************************************************************                 

def render_login():
    """Login al seleccionar Administración; protege los formularios de datos."""
    _, center, _ = st.columns([1, 2, 1])
    with center:
        st.title('📍 Servicios cercanos')
        st.caption('Inicia sesión para administrar los CESFAM y cargadores.')
        if 'login_notice' in st.session_state:
            st.info(st.session_state.pop('login_notice'))
        with st.container(border=True):
            st.subheader('🔒 Iniciar sesión')
            now = time.time()
            if not AUTH_PATH.is_file():
                st.info('Primero crea tu usuario desde la consola: python app.py --crear-admin')
            elif now < st.session_state.get('admin_block_until', 0):
                st.warning('Demasiados intentos. Espera un minuto y vuelve a intentar.')
            else:
                with st.form('admin_login', clear_on_submit=True):
                    username = st.text_input('Usuario', max_chars=100)
                    password = st.text_input('Contraseña', type='password', max_chars=256)
                    submitted = st.form_submit_button('Ingresar al administrador', type='primary', use_container_width=True)
                if submitted:
                    try:
                        valid = authenticate_with_version(username, password)
                    except (sqlite3.Error, OSError):
                        st.error('No se pudo consultar el archivo de usuarios.')
                        return
                    if valid:
                        st.session_state.admin_user = username.strip()
                        st.session_state.admin_credential_version = valid
                        st.session_state.admin_last_activity = now
                        st.session_state.admin_attempts = 0
                        st.session_state.app_screen = 'admin'
                        st.rerun()
                    else:
                        attempts = st.session_state.get('admin_attempts', 0) + 1
                        st.session_state.admin_attempts = attempts
                        if attempts >= 5:
                            st.session_state.admin_block_until = now + 60
                            st.session_state.admin_attempts = 0
                        st.error('Usuario o contraseña incorrectos.')
        st.button('← Volver al inicio', on_click=go_home, use_container_width=True)

#***************************************************************************************************************
# Muestra la tabla y los formularios para consultar, agregar, editar y eliminar establecimientos.
#***********************************************************************************************************     

def render_admin(on_change):
    if not session_is_active():
        render_login()
        return
    st.title('🔒 Administración')
    st.session_state.admin_last_activity = time.time()
    st.caption(f'Sesión: {st.session_state.admin_user}')
    with st.sidebar:
        st.header('Menú')
        st.button('🏠 Inicio', on_click=go_home, use_container_width=True)
        st.button('📍 Buscar servicios', on_click=open_public_search, use_container_width=True)
        st.button('Cerrar sesión', on_click=logout, use_container_width=True)
    if 'admin_notice' in st.session_state:
        st.success(st.session_state.pop('admin_notice'))
    kind = st.selectbox('Registros que quieres administrar', list(TABLES), key='admin_kind')
    operation = st.radio('Acción', ['Consultar', 'Agregar', 'Editar', 'Eliminar'], horizontal=True, key='admin_operation')
    query = st.text_input('Buscar por nombre, comuna, dirección o ID', key='admin_query')
    try:
        rows = list_records(kind, query)
    except (ValueError, sqlite3.Error, OSError) as exc:
        st.error(f'No se pudo leer la base de datos: {exc}')
        return
    st.caption(f'{len(rows)} registros encontrados')
    st.dataframe(rows, use_container_width=True, hide_index=True)
    if operation == 'Consultar':
        return
    original = None
    if operation in ('Editar', 'Eliminar'):
        if not rows:
            st.info('No hay registros para esta búsqueda.')
            return
        by_id = {r['id']: r for r in rows}
        selected = st.selectbox('Selecciona un registro', list(by_id), format_func=lambda i: f"{i} · {by_id[i]['nombre']}", key=f'admin_record_{kind}')
        snapshot_key = f'admin_snapshot_{kind}_{operation}'
        previous = st.session_state.get(snapshot_key)
        if previous is None or previous['id'] != selected:
            st.session_state[snapshot_key] = by_id[selected].copy()
        original = st.session_state[snapshot_key]
        if st.button('Recargar registro seleccionado'):
            st.session_state[snapshot_key] = by_id[selected].copy()
            for k in list(st.session_state):
                if k.startswith('admin_field_'):
                    del st.session_state[k]
            st.rerun()
    if operation == 'Eliminar':
        st.warning(f"Vas a eliminar el registro {original['id']}: {original['nombre']}.")
        with st.form(f"admin_delete_{kind}_{original['id']}"):
            confirmed = st.checkbox('Confirmo que quiero eliminar este registro')
            submitted = st.form_submit_button('Eliminar definitivamente')
        if submitted:
            if not confirmed:
                st.error('Marca la confirmación para eliminar.')
                return
            try:
                delete_record(kind, original)
            except (ValueError, sqlite3.Error, OSError) as exc:
                st.error(f'No se eliminó el registro: {exc}')
                return
            finish('Registro eliminado.', on_change)
        return
    record_id = original['id'] if original else 'nuevo'
    with st.form(f'admin_form_{kind}_{operation}_{record_id}'):
        values = {}
        for field in TABLES[kind][1]:
            value = original.get(field) if original else ''
            values[field] = st.text_input(LABELS[field], value='' if value is None else str(value), key=f'admin_field_{kind}_{operation}_{record_id}_{field}')
        st.caption('Coordenadas: usa punto decimal, por ejemplo -33.45 y -70.66.')
        submitted = st.form_submit_button('Guardar registro', type='primary')
    if submitted:
        try:
            save_record(kind, values, original)
        except (ValueError, sqlite3.Error, OSError) as exc:
            st.error(f'No se guardó el registro: {exc}')
            return
        finish('Registro guardado.', on_change)

#***************************************************************************************************************
# Limpia el estado de los formularios, solicita actualizar la búsqueda y muestra el mensaje de operación completada.
#***********************************************************************************************************     

def finish(message, on_change):
    on_change()
    for key in list(st.session_state):
        if key.startswith(('admin_snapshot_', 'admin_field_')):
            del st.session_state[key]
    st.session_state.admin_notice = message
    st.rerun()

import re
import pandas as pd
import streamlit as st

#***************************************
# Aplicación web y conversación          ********************************
#**************************************

#***************************************************************************************************************
# Configura el título y los estilos.
# Comprueba la sesión y muestra la pantalla seleccionada.
# Si corresponde a la búsqueda pública, muestra el menú lateral.
# Carga los establecimientos de la categoría elegida.
# Recupera y muestra el historial.
# Espera una dirección mediante st.chat_input().
# Busca sus coordenadas.
# Calcula los establecimientos más cercanos.
# Muestra y guarda la respuesta.
#***********************************************************************************************************     

def run_web():
    st.set_page_config(page_title='Servicios cercanos', page_icon='📍', layout='wide')
    st.markdown('\n<style>\n.cesfam-call {\n    display: inline-block;\n    padding: 0.35rem 0.7rem;\n    border-radius: 0.4rem;\n    background: #15803d;\n    color: #ffffff !important;\n    font-size: 14px;\n    font-weight: 600;\n    text-decoration: none !important;\n}\n.cesfam-call:hover { background: #166534; }\n.cesfam-call:focus-visible { outline: 3px solid #2563eb; outline-offset: 3px; }\n</style>\n', unsafe_allow_html=True)

    #***************************************************************************************************************
    # Limpia la caché y el historial de búsqueda después de modificar registros.
    #***********************************************************************************************************     
    def refresh_after_edit():
        st.cache_data.clear()
        for key in ('messages', 'active_category', 'address_input'):
            st.session_state.pop(key, None)
    session_is_active()
    screen = st.session_state.get('app_screen', 'home')
    if screen == 'home':
        render_home()
        st.stop()
    if screen == 'login':
        render_login()
        st.stop()
    if screen == 'admin':
        render_admin(refresh_after_edit)
        st.stop()
    with st.sidebar:
        st.button('🏠 Inicio', on_click=go_home, use_container_width=True)
        st.button('🔒 Administración', on_click=request_admin_login, use_container_width=True)
    st.title('📍 Encuentra CESFAM y CARGADORES CERCANOS ')
    st.caption('Selecciona qué quieres buscar en el menú lateral y escribe una dirección en Chile.')

    #***************************************************************************************************************
    # Elimina el historial, los resultados y la dirección de la sesión.
    #***********************************************************************************************************    

    def clear_search():
        """Reinicia la conversación de esta sesión y conserva la selección del menú."""
        st.session_state.pop('messages', None)
        st.session_state.pop('active_category', None)
        st.session_state.pop('address_input', None)
    with st.sidebar:
        st.header('Búsqueda')
        selection = st.radio('¿Qué quieres buscar?', ['Buscar CESFAM', 'Buscar Cargadores'])
        st.button('🔄 Refrescar y limpiar búsqueda', on_click=clear_search, use_container_width=True, help='Elimina la conversación, los resultados y los mapas para comenzar de nuevo.')
    category = 'cesfam' if selection == 'Buscar CESFAM' else 'cargadores'
    label = 'CESFAM' if category == 'cesfam' else 'cargadores'

    #***************************************************************************************************************
    # Carga CESFAM o cargadores según la categoría elegida. Utiliza caché
    #***********************************************************************************************************    

    @st.cache_data
    def places(kind: str, database_version: int):
        return load_cesfams() if kind == 'cesfam' else load_chargers()

    #***************************************************************************************************************
    # Consulta las coordenadas de una dirección y guarda el resultado en caché durante siete días.
    #***********************************************************************************************************    

    @st.cache_data(ttl=7 * 24 * 60 * 60, show_spinner=False)
    def resolve(address: str):
        return geocode_address(address)
    try:
        available = places(category, DB_PATH.stat().st_mtime_ns)
    except (OSError, ValueError, sqlite3.Error) as exc:
        st.error(f'No se pudo leer la base de datos: {exc}')
        st.stop()
    with st.sidebar:
        count = st.slider('Cantidad de resultados', min_value=3, max_value=10, value=5)
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    if st.session_state.get('active_category') != category:
        st.session_state.active_category = category
        st.session_state.messages.append({'role': 'assistant', 'text': f'Buscaremos {label} cercanos. ¿Cuál es tu dirección? Incluye calle, número y comuna.'})

    #***************************************************************************************************************
    # Revisa y prepara el teléfono para construir el enlace de llamada.
    #***********************************************************************************************************    

    def phone_to_dial(phone: str):
        """Prepara un teléfono chileno sin inventar dígitos faltantes."""
        phone = (phone or '').strip()
        if not re.fullmatch('\\+?[0-9 ()-]+', phone):
            return None
        digits = re.sub('[^0-9]', '', phone)
        if len(digits) == 11 and digits.startswith('56'):
            return '+' + digits
        if len(digits) == 9:
            return digits if digits.startswith(('600', '800')) else '+56' + digits
        return None

    #***************************************************************************************************************
    # Muestra el mensaje, el mapa, la lista de establecimientos y los botones de ubicación y llamada.
    #***********************************************************************************************************    

    def show_response(message):
        st.write(message['text'])
        if 'results' not in message:
            return
        found = message['results']
        result_category = message['category']
        origin_lat, origin_lon = message['origin']
        point_color = '#16a34a' if result_category == 'cesfam' else '#e11d48'
        result_label = 'CESFAM' if result_category == 'cesfam' else 'cargadores'
        map_rows = [{'lat': origin_lat, 'lon': origin_lon, 'color': '#2563eb', 'size': 130}]
        map_rows.extend(({'lat': p.latitud, 'lon': p.longitud, 'color': point_color, 'size': 100} for p in found))
        st.map(pd.DataFrame(map_rows), latitude='lat', longitude='lon', color='color', size='size')
        color_name = 'Verde' if result_category == 'cesfam' else 'Rosa'
        st.caption(f'Azul: dirección consultada · {color_name}: {result_label}. Distancias en línea recta, no por calles. Mapa: © OpenStreetMap contributors.')
        for idx, place in enumerate(found, start=1):
            name = place.nombre if place.nombre.lower() != 'undefined' else 'Establecimiento sin nombre'
            st.markdown(f'**{idx}. {name} — {place.distancia_km:.2f} km**')
            st.write(f'{place.direccion} · {place.comuna} · {place.region}')
            if result_category == 'cesfam':
                st.write(f'Teléfono de contacto: {place.telefono}')
            else:
                st.caption(f'Conector: {place.tipo_conector} · Potencia: {place.potencia_kw}')
            st.link_button('📍 Ver ubicación en OpenStreetMap', f'https://www.openstreetmap.org/?mlat={place.latitud}&mlon={place.longitud}#map=17/{place.latitud}/{place.longitud}', type='primary')
            if result_category == 'cesfam':
                dial_number = phone_to_dial(place.telefono)
                if dial_number:
                    st.markdown(f'<a class="cesfam-call" href="tel:{dial_number}" target="_self">📞 Llamar al {dial_number}</a>', unsafe_allow_html=True)
                elif place.telefono != 'No informado':
                    st.caption('El número registrado está incompleto o tiene un formato no reconocido.')
    for message in st.session_state.messages:
        with st.chat_message(message['role']):
            show_response(message)
    if (address := st.chat_input(f'Escribe tu dirección para buscar {label}', max_chars=200, key='address_input')):
        address = address.strip()
        st.session_state.messages.append({'role': 'user', 'text': address})
        with st.chat_message('user'):
            st.write(address)
        with st.chat_message('assistant'):
            with st.spinner(f'Buscando la dirección y los {label} más cercanos...'):
                try:
                    point = resolve(address)
                    if point is None:
                        reply = {'role': 'assistant', 'text': 'No encontré esa dirección en Chile. Prueba con calle, número y comuna.'}
                    elif not available:
                        reply = {'role': 'assistant', 'text': f'No hay {label} con coordenadas disponibles.'}
                    else:
                        lat, lon, resolved_name = point
                        search = nearest_cesfams if category == 'cesfam' else nearest_chargers
                        found = search(available, lat, lon, count)
                        reply = {'role': 'assistant', 'id': len(st.session_state.messages), 'category': category, 'text': f'Encontré esta ubicación: {resolved_name}. Estos son los {len(found)} {label} más cercanos:', 'origin': (lat, lon), 'results': found}
                except GeocodingError as exc:
                    reply = {'role': 'assistant', 'text': str(exc)}
            show_response(reply)
        st.session_state.messages.append(reply)

#*************************************************************************
# GESTIÓN DE ADMINISTRADORES: sólo desde la consola del equipo.            **************************
#*************************************************************************

#***************************************************************************************************************
# Valida la contraseña con scrypt y devuelve una huella de las credenciales si son correctas.
#*********************************************************************************************************** 

def authenticate_with_version(username, password, path=AUTH_PATH):
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as db:
        row = db.execute('SELECT salt, password_hash FROM administradores WHERE username=?',
                         (username.strip(),)).fetchone()
    salt, expected = row if row else (b'\0' * 16, b'\0' * 32)
    actual = password_hash(password, salt)
    if row is not None and hmac.compare_digest(actual, expected):
        return hashlib.sha256(salt + expected).hexdigest()
    return None

#***************************************************************************************************************
# Obtiene la huella de las credenciales actuales para detectar cambios o eliminaciones.
#*********************************************************************************************************** 

def credential_version(username, path=AUTH_PATH):
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as db:
        row = db.execute('SELECT salt, password_hash FROM administradores WHERE username=?',
                         (username.strip(),)).fetchone()
    return hashlib.sha256(row[0] + row[1]).hexdigest() if row else None

#***************************************************************************************************************
# Elimina de SQLite al administrador indicado.
#*********************************************************************************************************** 

def delete_admin(username, path=AUTH_PATH):
    with sqlite3.connect(path.resolve().as_uri() + '?mode=rw', uri=True) as db:
        cursor = db.execute('DELETE FROM administradores WHERE username=?', (username.strip(),))
        if cursor.rowcount != 1:
            raise ValueError('No existe ese administrador.')

#***************************************************************************************************************
# Crea un administrador nuevo y elimina el anterior dentro de una misma transacción.
#*********************************************************************************************************** 

def replace_admin(old_username, new_username, password, path=AUTH_PATH):
    """Crea el reemplazo y elimina al anterior en una misma transacción."""
    old_username, new_username = old_username.strip(), new_username.strip()
    if not new_username or len(new_username) > 100:
        raise ValueError('El usuario nuevo debe tener entre 1 y 100 caracteres.')
    if new_username == old_username:
        raise ValueError('Usa otro nombre de usuario o utiliza --reset para cambiar la contraseña.')
    if len(password) < 12:
        raise ValueError('Usa una contraseña de al menos 12 caracteres.')
    salt = secrets.token_bytes(16)
    digest = password_hash(password, salt)
    with sqlite3.connect(path.resolve().as_uri() + '?mode=rw', uri=True) as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT INTO administradores(username,salt,password_hash) VALUES (?,?,?)',
                   (new_username, salt, digest))
        cursor = db.execute('DELETE FROM administradores WHERE username=?', (old_username,))
        if cursor.rowcount != 1:
            raise ValueError('No existe el administrador anterior. No se aplicaron cambios.')

#***************************************************************************************************************
# Interpreta los comandos de CMD y solicita los datos necesarios.
#*********************************************************************************************************** 

def admin_cli():
    parser = argparse.ArgumentParser(description='Gestión local del chatbot. Inicia la web con: python -m streamlit run app.py')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--crear-admin', action='store_true', help='Crear administrador')
    group.add_argument('--eliminar-admin', action='store_true', help='Eliminar administrador')
    group.add_argument('--reemplazar-admin', action='store_true', help='Crear otro y eliminar el anterior en una operación')
    group.add_argument('--reset', action='store_true', help='Restablecer contraseña')
    group.add_argument('--listar-admins', action='store_true', help='Mostrar sólo los nombres de usuario')
    group.add_argument('--importar-cesfam', type=Path, help='Importar o actualizar CESFAM desde GeoJSON')
    args = parser.parse_args()
    try:
        if args.importar_cesfam:
            print(f'CESFAM importados o actualizados: {import_cesfams(args.importar_cesfam)}')
            return
        if args.listar_admins:
            with sqlite3.connect(DB_PATH.resolve().as_uri() + '?mode=ro', uri=True) as db:
                names = db.execute('SELECT username FROM administradores ORDER BY username').fetchall()
            for (name,) in names:
                print(name)
            if not names:
                print('No hay administradores. Usa python app.py --crear-admin')
            return
        if args.eliminar_admin or args.reemplazar_admin:
            old = input('Usuario que se eliminará: ').strip()
            if input('Para confirmar, escribe nuevamente ese usuario: ').strip() != old or not old:
                raise ValueError('Confirmación incorrecta. No se aplicaron cambios.')
            if args.eliminar_admin:
                delete_admin(old)
                print('Administrador eliminado. Puedes crear otro con: python app.py --crear-admin')
                return
            user = input('Nombre del nuevo administrador: ')
        else:
            user = input('Usuario: ')
        password = getpass.getpass('Nueva contraseña (mínimo 12 caracteres): ')
        confirmation = getpass.getpass('Repetir contraseña: ')
        if password != confirmation:
            raise ValueError('Las contraseñas no coinciden. No se aplicaron cambios.')
        if args.reemplazar_admin:
            replace_admin(old, user, password)
        else:
            create_admin(user, password, reset=args.reset)
        print('Cambio guardado. Inicia sesión con las nuevas credenciales.')
    except (ValueError, sqlite3.Error, OSError) as exc:
        raise SystemExit(f'No se completó la operación: {exc}') from None


if __name__ == '__main__':
    from streamlit.runtime.scriptrunner import get_script_run_ctx
    if get_script_run_ctx(suppress_warning=True) is not None:
        run_web()
    else:
        admin_cli()
