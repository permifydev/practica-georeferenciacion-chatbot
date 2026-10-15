"""Chatbot local: menú de CESFAM o cargadores, dirección, lista y mapa."""
import sqlite3
import re
import pandas as pd
import streamlit as st
from charger_data import DB_PATH, load_chargers, nearest_chargers
from cesfam_data import load_cesfams, nearest_cesfams
from geocoding import GeocodingError, geocode_address

st.set_page_config(page_title='Servicios cercanos', page_icon='📍', layout='wide')
st.markdown('''
<style>
.cesfam-call {
    display: inline-block;
    padding: 0.35rem 0.7rem;
    border-radius: 0.4rem;
    background: #15803d;
    color: #ffffff !important;
    font-size: 14px;
    font-weight: 600;
    text-decoration: none !important;
}
.cesfam-call:hover { background: #166534; }
.cesfam-call:focus-visible { outline: 3px solid #2563eb; outline-offset: 3px; }
</style>
''', unsafe_allow_html=True)
# La administración se procesa antes de cargar o mostrar la búsqueda pública.
from admin_ui import render_admin, render_login, render_home, session_is_active, go_home, request_admin_login

def refresh_after_edit():
    st.cache_data.clear()
    for key in ('messages', 'active_category', 'address_input'):
        st.session_state.pop(key, None)

# El inicio ofrece búsqueda pública y acceso al administrador con credenciales.
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

def clear_search():
    """Reinicia la conversación de esta sesión y conserva la selección del menú."""
    st.session_state.pop('messages', None)
    st.session_state.pop('active_category', None)
    st.session_state.pop('address_input', None)

with st.sidebar:
    st.header('Búsqueda')
    selection = st.radio('¿Qué quieres buscar?', ['Buscar CESFAM', 'Buscar Cargadores'])
    st.button('🔄 Refrescar y limpiar búsqueda', on_click=clear_search,
              use_container_width=True,
              help='Elimina la conversación, los resultados y los mapas para comenzar de nuevo.')

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
    count = st.slider('Cantidad de resultados', min_value=3, max_value=10, value=5)
   

if 'messages' not in st.session_state:
    st.session_state.messages = []
if st.session_state.get('active_category') != category:
    st.session_state.active_category = category
    st.session_state.messages.append({
        'role': 'assistant',
        'text': f'Buscaremos {label} cercanos. ¿Cuál es tu dirección? Incluye calle, número y comuna.',
    })

def phone_to_dial(phone: str):
    """Prepara un teléfono chileno sin inventar dígitos faltantes."""
    phone = (phone or '').strip()
    if not re.fullmatch(r'\+?[0-9 ()-]+', phone):
        return None
    digits = re.sub(r'[^0-9]', '', phone)
    if len(digits) == 11 and digits.startswith('56'):
        return '+' + digits
    if len(digits) == 9:
        # Los números de servicio se marcan en su formato nacional.
        return digits if digits.startswith(('600', '800')) else '+56' + digits
    return None


def show_response(message):
    st.write(message['text'])

    if 'results' not in message:
        return

    found = message['results']
    result_category = message['category']
    origin_lat, origin_lon = message['origin']

    point_color = '#16a34a' if result_category == 'cesfam' else '#e11d48'
    result_label = 'CESFAM' if result_category == 'cesfam' else 'cargadores'

    map_rows = [
        {
            'lat': origin_lat,
            'lon': origin_lon,
            'color': '#2563eb',
            'size': 130
        }
    ]

    map_rows.extend(
        {
            'lat': p.latitud,
            'lon': p.longitud,
            'color': point_color,
            'size': 100
        }
        for p in found
    )

    st.map(
        pd.DataFrame(map_rows),
        latitude='lat',
        longitude='lon',
        color='color',
        size='size'
    )

    color_name = 'Verde' if result_category == 'cesfam' else 'Rosa'

    st.caption(
        f'Azul: dirección consultada · {color_name}: {result_label}. '
        'Distancias en línea recta, no por calles. '
        'Mapa: © OpenStreetMap contributors.'
    )

    for idx, place in enumerate(found, start=1):
        name = (
            place.nombre
            if place.nombre.lower() != 'undefined'
            else 'Establecimiento sin nombre'
        )

        st.markdown(
            f'**{idx}. {name} — {place.distancia_km:.2f} km**'
        )
        st.write(
            f'{place.direccion} · {place.comuna} · {place.region}'
        )

        if result_category == 'cesfam':
            st.write(f'Teléfono de contacto: {place.telefono}')
        else:
            st.caption(
                f'Conector: {place.tipo_conector} · '
                f'Potencia: {place.potencia_kw}'
            )

        st.link_button(
            '📍 Ver ubicación en OpenStreetMap',
            f'https://www.openstreetmap.org/?mlat={place.latitud}&mlon={place.longitud}#map=17/{place.latitud}/{place.longitud}',
            type='primary'
        )

        # Botón pequeño debajo de Ver ubicación.
        if result_category == 'cesfam':
            dial_number = phone_to_dial(place.telefono)

            if dial_number:
                st.markdown(
                    f'<a class="cesfam-call" '
                    f'href="tel:{dial_number}" target="_self">'
                    f'📞 Llamar al {dial_number}</a>',
                    unsafe_allow_html=True
                )
            elif place.telefono != 'No informado':
                st.caption(
                    'El número registrado está incompleto '
                    'o tiene un formato no reconocido.'
                )

for message in st.session_state.messages:
    with st.chat_message(message['role']):
        show_response(message)

if address := st.chat_input(f'Escribe tu dirección para buscar {label}', max_chars=200, key='address_input'):
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
