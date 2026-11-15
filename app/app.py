"""Detector de huella humana - interfaz.

  streamlit run app/app.py

Estructura: theme (paleta y estilos), ui (componentes y SVG animados), data (carga con cache), nav (navegacion)
y views/ (una vista por archivo). Lee los resultados del motor en data/real y del barrido nacional en data/national.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # para importar el paquete uma (auditoria)

import streamlit as st  # noqa: E402

st.set_page_config(page_title="Detector de huella humana", layout="wide", initial_sidebar_state="collapsed")

import data  # noqa: E402
import nav  # noqa: E402
import theme  # noqa: E402
import ui  # noqa: E402
from views import asistente, cerca, ficha, mapa, monitoreo, panorama, verificacion, vigilancia  # noqa: E402

theme.apply()
nav.init()

results = data.results()
if not results:
    st.error(f"No hay resultados en {data.DATA}. Corre primero: python run_engine.py")
    st.stop()
by_id = {r["body_id"]: r for r in results}
controls = data.controls(results)
national = data.national()

top_l, top_r = st.columns([5, 2])
with top_l:
    st.segmented_control("Vista", nav.VIEWS, key="nav", label_visibility="collapsed")
    ui.md(ui.nav_icon_css("nav", nav.ICONS))
with top_r:
    show_ctrl = st.toggle("Mostrar gemelas de control", value=False)
if data.DATA.name == "sample":
    st.warning("Datos de prueba ficticios. No usar estos numeros en el pitch.")

visible = [r for r in results if show_ctrl or r["body_id"] not in controls or r["state"] == "Huella humana"]
options = [r["body_id"] for r in visible]
if st.session_state.sel not in options:
    st.session_state.sel = None

view = st.session_state.nav or nav.VIEWS[0]
if view == "Panorama":
    panorama.render(results, visible, national)
elif view == "Mapa":
    mapa.render(visible, by_id, national)
elif view == "Cerca de mi":
    cerca.render(results, national, by_id)
elif view == "Pregunta":
    asistente.render(results, national, by_id)
elif view == "Verificacion":
    verificacion.render(results)
elif view == "Monitoreo":
    monitoreo.render(results, national)
elif view == "Ficha":
    ficha.render(options, by_id)
else:
    vigilancia.render()

st.caption("El detector prueba coincidencia y consistencia, no causalidad estricta. Datos: Landsat 5/7/8/9 (NASA/USGS), "
           "NASA POWER, NASA FIRMS, MODIS MCD64A1 y MOD16, GRACE, NASADEM, NOAA ONI, CHIRPS, ERA5-Land, JRC Global "
           "Surface Water, MapBiomas Bolivia y MapBiomas Agua, Hansen GFC 2025, DMSP/VIIRS, WorldPop, HydroBASINS, "
           "OpenStreetMap.")
