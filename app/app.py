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

st.segmented_control("Vista", nav.VIEWS, key="nav", label_visibility="collapsed")
ui.md(ui.nav_icon_css("nav", nav.ICONS))
if data.DATA.name == "sample":
    st.warning("Datos de prueba ficticios. No usar estos numeros en el pitch.")

visible = [r for r in results if data.is_main(r, controls)]
# en la ficha se puede abrir todo: casos principales primero, despues gemelas y lagunas de calibracion
options = [r["body_id"] for r in visible] + [r["body_id"] for r in results if r not in visible]
if st.session_state.sel not in options:
    st.session_state.sel = None

view = st.session_state.nav or nav.VIEWS[0]
if view == "Inicio":
    panorama.render(results, visible, national)
elif view == "Mapa":
    mapa.render(visible, by_id, national)
elif view == "Cerca de mi":
    cerca.render(results, national, by_id)
elif view == "Pregunta":
    asistente.render(results, national, by_id)
elif view == "Ficha":
    ficha.render(options, by_id)
else:
    t1, t2, t3 = st.tabs(["Como lo verificamos", "Todas las lagunas", "Vigilancia de incendios"])
    with t1:
        verificacion.render(results)
    with t2:
        monitoreo.render(results, national)
    with t3:
        vigilancia.render()

st.caption("Muestra coincidencias y consistencia en el tiempo, no prueba causalidad estricta. Datos satelitales de la "
           "NASA y otras 15 fuentes abiertas: el detalle esta en Datos y metodo.")
