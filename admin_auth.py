"""Usuarios locales con hash scrypt. Crear/cambiar contraseña desde la consola."""
import argparse
import getpass
import hashlib
import hmac
from pathlib import Path
import secrets
import sqlite3

AUTH_PATH = Path(__file__).parent / 'administradores.sqlite3'

def password_hash(password, salt):
    return hashlib.scrypt(password.encode('utf-8'), salt=salt, n=16384, r=8, p=1, dklen=32)

def authenticate(username, password, path=AUTH_PATH):
    if not path.is_file():
        return False
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as db:
        row = db.execute('SELECT salt, password_hash FROM administradores WHERE username=?', (username.strip(),)).fetchone()
    # Hace el mismo cálculo para usuarios inexistentes.
    salt, expected = row if row else (b'\0' * 16, b'\0' * 32)
    actual = password_hash(password, salt)
    return row is not None and hmac.compare_digest(actual, expected)

def create_admin(username, password, path=AUTH_PATH, reset=False):
    username = username.strip()
    if not username or len(username) > 100:
        raise ValueError('El usuario debe tener entre 1 y 100 caracteres.')
    if len(password) < 12:
        raise ValueError('Usa una contraseña de al menos 12 caracteres.')
    salt = secrets.token_bytes(16)
    digest = password_hash(password, salt)
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS administradores (username TEXT PRIMARY KEY, salt BLOB NOT NULL, password_hash BLOB NOT NULL)')
        if reset:
            cursor = db.execute('UPDATE administradores SET salt=?, password_hash=? WHERE username=?', (salt, digest, username))
            if cursor.rowcount != 1:
                raise ValueError('No existe ese usuario.')
        else:
            db.execute('INSERT INTO administradores VALUES (?, ?, ?)', (username, salt, digest))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Crear administrador local o cambiar su contraseña.')
    parser.add_argument('--reset', action='store_true', help='Cambiar contraseña de un usuario existente')
    args = parser.parse_args()
    user = input('Usuario: ')
    password = getpass.getpass('Contraseña (mínimo 12 caracteres): ')
    confirmation = getpass.getpass('Repetir contraseña: ')
    try:
        if password != confirmation:
            raise ValueError('Las contraseñas no coinciden.')
        create_admin(user, password, reset=args.reset)
    except (ValueError, sqlite3.Error) as exc:
        raise SystemExit(f'No se guardó el usuario: {exc}')
    print('Usuario guardado. Ya puedes iniciar sesión en Administración.')
