"""Local Streamlit chatbot: entered address -> nearest charger list and map."""

import pandas as pd
import streamlit as st

from charger_data import load_chargers, nearest_chargers
from geocoding import GeocodingError, geocode_address


st.set_page_config(page_title="Cargadores cercanos", page_icon="🔌", layout="wide")
st.title("🔌 Cargadores eléctricos cercanos")
st.caption("Escribe una dirección en Chile para encontrar cargadores en la copia local de la base de datos.")


@st.cache_data
def chargers():
    return load_chargers()


@st.cache_data(ttl=7 * 24 * 60 * 60, show_spinner=False)
def resolve(address: str):
    return geocode_address(address)


try:
    available = chargers()
except (OSError, ValueError) as exc:
    st.error(f"No se pudo leer la copia de la base de datos: {exc}")
    st.stop()

with st.sidebar:
    st.header("Búsqueda")
    count = st.slider("Cantidad de cargadores", min_value=3, max_value=10, value=5)
    st.write(f"Cargadores con coordenadas: **{len(available)}**")
    st.caption("La base se consulta solo en modo lectura.")

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "text": "¿Cuál es tu dirección? Incluye calle, número y comuna, por ejemplo: Av. Providencia 1234, Providencia, Chile."}]


def show_response(message):
    st.write(message["text"])
    if "results" not in message:
        return
    found = message["results"]
    origin_lat, origin_lon = message["origin"]
    map_rows = [{"lat": origin_lat, "lon": origin_lon, "color": "#2563eb", "size": 130}]
    map_rows.extend({"lat": c.latitud, "lon": c.longitud, "color": "#e11d48", "size": 100} for c in found)
    st.map(pd.DataFrame(map_rows), latitude="lat", longitude="lon", color="color", size="size")
    st.caption("Azul: dirección consultada · Rosa: cargadores · Distancias aproximadas en línea recta (no por calles). Mapa: © OpenStreetMap contributors.")
    for idx, c in enumerate(found, start=1):
        name = c.nombre if c.nombre.lower() != "undefined" else "Cargador sin nombre"
        st.markdown(f"**{idx}. {name} — {c.distancia_km:.2f} km**")
        st.write(f"{c.direccion} · {c.comuna} · {c.region}")
        st.caption(f"Conector: {c.tipo_conector} · Potencia: {c.potencia_kw}")
        st.link_button("Ver ubicación en OpenStreetMap", f"https://www.openstreetmap.org/?mlat={c.latitud}&mlon={c.longitud}#map=17/{c.latitud}/{c.longitud}", key=f"place_{message['id']}_{c.id}")


for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        show_response(message)

if address := st.chat_input("Escribe tu dirección en Chile"):
    address = address.strip()
    st.session_state.messages.append({"role": "user", "text": address})
    with st.chat_message("user"):
        st.write(address)
    with st.chat_message("assistant"):
        with st.spinner("Buscando la dirección y los cargadores más cercanos..."):
            try:
                point = resolve(address)
                if point is None:
                    reply = {"role": "assistant", "text": "No encontré esa dirección en Chile. Prueba con calle, número y comuna."}
                else:
                    lat, lon, resolved_name = point
                    found = nearest_chargers(available, lat, lon, count)
                    reply = {"role": "assistant", "id": len(st.session_state.messages),
                             "text": f"Encontré esta ubicación: {resolved_name}. Estos son los {len(found)} cargadores más cercanos:",
                             "origin": (lat, lon), "results": found}
            except GeocodingError as exc:
                reply = {"role": "assistant", "text": str(exc)}
        show_response(reply)
    st.session_state.messages.append(reply)
