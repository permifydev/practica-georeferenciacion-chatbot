"""Pantalla privada: autenticar antes de consultar o modificar registros."""
import sqlite3
import time
import streamlit as st
from admin_auth import AUTH_PATH, authenticate
from admin_data import TABLES, list_records, save_record, delete_record

LABELS = {'nombre': 'Nombre', 'direccion': 'Dirección', 'comuna': 'Comuna', 'region': 'Región', 'latitud': 'Latitud', 'longitud': 'Longitud', 'telefono': 'Teléfono', 'tipo_conector': 'Tipo de conector', 'potencia_kw': 'Potencia (kW)'}

def logout():
    for key in list(st.session_state):
        if key.startswith('admin_') and key not in ('admin_attempts', 'admin_block_until'):
            del st.session_state[key]
    st.session_state.app_screen = 'home'


def session_is_active():
    """Comprueba vencimiento antes de acceder a cualquier pantalla privada."""
    if not st.session_state.get('admin_user'):
        return False
    if time.time() - st.session_state.get('admin_last_activity', 0) > 1800:
        logout()
        st.session_state.app_screen = 'login'
        st.session_state.login_notice = 'La sesión expiró por inactividad. Inicia sesión nuevamente.'
        return False
    return True


def open_public_search():
    st.session_state.app_screen = 'public'


def go_home():
    st.session_state.app_screen = 'home'


def request_admin_login():
    # Cada entrada desde el botón Administración exige credenciales nuevamente.
    logout()
    st.session_state.app_screen = 'login'


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
                st.info('Primero crea tu usuario desde la consola: python admin_auth.py')
            elif now < st.session_state.get('admin_block_until', 0):
                st.warning('Demasiados intentos. Espera un minuto y vuelve a intentar.')
            else:
                with st.form('admin_login', clear_on_submit=True):
                    username = st.text_input('Usuario', max_chars=100)
                    password = st.text_input('Contraseña', type='password', max_chars=256)
                    submitted = st.form_submit_button('Ingresar al administrador', type='primary', use_container_width=True)
                if submitted:
                    try:
                        valid = authenticate(username, password)
                    except (sqlite3.Error, OSError):
                        st.error('No se pudo consultar el archivo de usuarios.')
                        return
                    if valid:
                        st.session_state.admin_user = username.strip()
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


def render_admin(on_change):
    # Protección adicional aunque se invoque esta función desde otra pantalla.
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
        selected = st.selectbox('Selecciona un registro', list(by_id), format_func=lambda i: f'{i} · {by_id[i]["nombre"]}', key=f'admin_record_{kind}')
        # Mantiene una copia de lo que se presentó, para detectar cambios concurrentes.
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
        st.warning(f'Vas a eliminar el registro {original["id"]}: {original["nombre"]}.')
        with st.form(f'admin_delete_{kind}_{original["id"]}'):
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

def finish(message, on_change):
    on_change()
    for key in list(st.session_state):
        if key.startswith(('admin_snapshot_', 'admin_field_')):
            del st.session_state[key]
    st.session_state.admin_notice = message
    st.rerun()
