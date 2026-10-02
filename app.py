"""Chatbot local: menú de CESFAM o cargadores, dirección, lista y mapa."""
import sqlite3
import pandas as pd
import streamlit as st
from charger_data import DB_PATH, load_chargers, nearest_chargers
from cesfam_data import load_cesfams, nearest_cesfams
from geocoding import GeocodingError, geocode_address

st.set_page_config(page_title='Servicios cercanos', page_icon='📍', layout='wide')
st.title('📍 Encuentra CESFAM y cargadores cercanos')
st.caption('Selecciona qué quieres buscar y escribe una dirección en Chile.')

selection = st.radio('¿Qué quieres buscar?', ['Buscar CESFAM', 'Buscar cargadores'], horizontal=True)
category = 'cesfam' if selection == 'Buscar CESFAM' else 'cargadores'
label = 'CESFAM' if category == 'cesfam' else 'cargadores'

@st.cache_data
def places(kind: str, database_version: int):
    # La fecha de modificación invalida la caché si cambia el archivo SQLite.
    return load_cesfams() if kind == 'cesfam' else load_chargers()

@st.cache_data(ttl=7 * 24 * 60 * 60, show_spinner=False)
def resolve(address: str):
    return geocode_address(address)

try:
    available = places(category, DB_PATH.stat().st_mtime_ns)
except (OSError, ValueError, sqlite3.Error) as exc:
    st.error(f'No se pudo leer la base de datos: {exc}')
    st.stop()

with st.sidebar:
    st.header('Búsqueda')
    count = st.slider('Cantidad de resultados', min_value=3, max_value=10, value=5)
    st.write(f'{label} con coordenadas: **{len(available)}**')
    st.caption('Distancias aproximadas en línea recta.')

if 'messages' not in st.session_state:
    st.session_state.messages = []
if st.session_state.get('active_category') != category:
    st.session_state.active_category = category
    st.session_state.messages.append({
        'role': 'assistant',
        'text': f'Buscaremos {label} cercanos. ¿Cuál es tu dirección? Incluye calle, número y comuna.',
    })

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
    map_rows.extend({'lat': p.latitud, 'lon': p.longitud, 'color': point_color, 'size': 100} for p in found)
    st.map(pd.DataFrame(map_rows), latitude='lat', longitude='lon', color='color', size='size')
    color_name = 'Verde' if result_category == 'cesfam' else 'Rosa'
    st.caption(f'Azul: dirección consultada · {color_name}: {result_label}. Distancias en línea recta, no por calles. Mapa: © OpenStreetMap contributors.')
    for idx, place in enumerate(found, start=1):
        name = place.nombre if place.nombre.lower() != 'undefined' else 'Cargador sin nombre'
        st.markdown(f'**{idx}. {name} — {place.distancia_km:.2f} km**')
        st.write(f'{place.direccion} · {place.comuna} · {place.region}')
        if result_category == 'cesfam':
            st.caption(f'Teléfono: {place.telefono}')
        else:
            st.caption(f'Conector: {place.tipo_conector} · Potencia: {place.potencia_kw}')
        st.link_button('Ver ubicación en OpenStreetMap',
            f'https://www.openstreetmap.org/?mlat={place.latitud}&mlon={place.longitud}#map=17/{place.latitud}/{place.longitud}')

for message in st.session_state.messages:
    with st.chat_message(message['role']):
        show_response(message)

if address := st.chat_input(f'Escribe tu dirección para buscar {label}', max_chars=200):
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
                    reply = {'role': 'assistant', 'id': len(st.session_state.messages),
                        'category': category,
                        'text': f'Encontré esta ubicación: {resolved_name}. Estos son los {len(found)} {label} más cercanos:',
                        'origin': (lat, lon), 'results': found}
            except GeocodingError as exc:
                reply = {'role': 'assistant', 'text': str(exc)}
        show_response(reply)
    st.session_state.messages.append(reply)
