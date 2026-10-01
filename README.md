# Chatbot local de cargadores eléctricos

Proyecto separado en Python 3.12.10 y Streamlit. Solicita una dirección en Chile,
consulta su ubicación mediante Nominatim y presenta los cargadores cercanos
de una copia local de la tabla `cargadores_cargadorelectrico` en lista y mapa.

## Ejecutar en Windows (PowerShell)

Abre una terminal en esta carpeta y ejecuta:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python --version
pip install -r requirements.txt
streamlit run app.py
```

`python --version` debe mostrar Python 3.12.x; para coincidir exactamente con
Addrss, instala y selecciona 3.12.10. El navegador abrirá una URL local,
normalmente `http://localhost:8501`.

Si PowerShell impide activar el entorno, ejecuta los comandos mediante
`.venv\Scripts\python.exe -m pip install -r requirements.txt` y
`.venv\Scripts\python.exe -m streamlit run app.py`.

## Datos y cálculo

- `cargadores.sqlite3` contiene únicamente la tabla de cargadores de la copia
  suministrada. No incluye usuarios, contraseñas ni sesiones. Se abre en modo lectura.
- De los 270 registros originales, 186 tienen coordenadas y participan en la búsqueda.
- La dirección se convierte a coordenadas con el servicio público de Nominatim.
  Requiere conexión a Internet. Las consultas repetidas se guardan temporalmente
  en la caché de Streamlit durante siete días.
- Se usa la fórmula de Haversine para ordenar por distancia geográfica aproximada.
  No calcula rutas ni distancias por calles.
- El servicio público de Nominatim tiene límites de uso y corresponde a este
  prototipo local de bajo volumen.

## Archivos

- `app.py`: conversación, lista y mapa.
- `charger_data.py`: lectura de SQLite y cálculo de cercanía.
- `geocoding.py`: búsqueda de la dirección mediante Nominatim.
- `cargadores.sqlite3`: copia de los datos necesarios para este prototipo.
