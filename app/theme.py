"""Tema visual: paleta, estilos globales, particulas de fondo y animaciones SVG.

Paleta amable sobre indigo profundo: colores suaves pero distinguibles por estado, agua natural en azul
profundo y agua artificial en celeste neon (pedido del equipo).
"""
from __future__ import annotations

import altair as alt
import streamlit as st

# ------------------------------------------------------------------ paleta
BG = "#0e1428"          # fondo
SURFACE = "#171f3a"     # tarjetas
SURFACE_2 = "#1f2950"   # tarjetas resaltadas
BORDER = "rgba(148, 163, 255, 0.14)"
TEXT = "#eef1fb"
MUTED = "#a3abc9"
ACCENT = "#5eead4"      # turquesa (marca)
ACCENT_2 = "#a5b4fc"    # lavanda
NATURAL = "#2563eb"     # agua natural: azul profundo
ARTIFICIAL = "#22e5ff"  # agua artificial: celeste neon
INK = "#121528"         # texto sobre colores

STATES = {  # color e icono Lucide de cada estado
    "Huella humana": {"color": "#ff7a7a", "icon": "footprints"},
    "Alerta temprana": {"color": "#c4a1ff", "icon": "siren"},
    "Incalculable": {"color": "#ffd166", "icon": "circle-help"},
    "Aguas arriba": {"color": "#60a5fa", "icon": "waves"},
    "Causa climatica": {"color": "#ffa26b", "icon": "cloud-sun-rain"},
    "Intacto": {"color": "#5ee6a8", "icon": "shield-check"},
}
SEVERITY = {s: i for i, s in enumerate(STATES)}
ACTION = {
    "Huella humana": "Prevenir: controlar la actividad sospechosa, proteger la cuenca y restaurar.",
    "Alerta temprana": "Actuar ya, cuando proteger todavia es barato.",
    "Incalculable": "Revisar: el agua cae, pero con los datos disponibles no se puede calcular la causa con "
                    "confianza. Los motivos explican que falta.",
    "Aguas arriba": "Mirar la fuente: le llega menos agua por el rio. Cuidar el rio y la laguna que la alimenta, "
                    "y controlar lo que se saca en el camino.",
    "Causa climatica": "Adaptarse: cosecha de agua, reservorios y planes de sequia.",
    "Intacto": "Seguimiento.",
}


def state_color(state: str) -> str:
    return STATES.get(state, STATES["Incalculable"])["color"]


def state_rgb(state: str) -> list[int]:
    h = state_color(state).lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


# ------------------------------------------------------------------ estilos globales
CSS = f"""
<style>
:root {{ --bg:{BG}; --surface:{SURFACE}; --surface2:{SURFACE_2}; --border:{BORDER}; --text:{TEXT};
        --muted:{MUTED}; --accent:{ACCENT}; --accent2:{ACCENT_2}; --ink:{INK}; }}
html, body, .stApp {{ background: radial-gradient(1200px 700px at 15% -10%, #23306b 0%, transparent 60%),
                     radial-gradient(900px 600px at 110% 10%, #1b4a5e 0%, transparent 55%), var(--bg) !important;
                     color: var(--text); }}
[data-testid="stAppViewContainer"], [data-testid="stHeader"] {{ background: transparent !important; }}
.block-container {{ padding-top: 3.4rem; padding-bottom: 2rem; max-width: 1400px; position: relative; z-index: 1; }}
section[data-testid="stSidebar"] {{ display: none; }}

/* particulas: dos capas de puntos que flotan lento detras de todo */
.stApp::before, .stApp::after {{ content:""; position:fixed; inset:-50%; pointer-events:none; z-index:0;
  background-image: radial-gradient(2px 2px at 20% 30%, rgba(165,180,252,.55) 50%, transparent 51%),
    radial-gradient(1.5px 1.5px at 70% 60%, rgba(94,234,212,.5) 50%, transparent 51%),
    radial-gradient(2.5px 2.5px at 40% 80%, rgba(34,229,255,.35) 50%, transparent 51%),
    radial-gradient(1.5px 1.5px at 85% 15%, rgba(255,255,255,.35) 50%, transparent 51%),
    radial-gradient(2px 2px at 10% 70%, rgba(196,161,255,.4) 50%, transparent 51%);
  background-size: 380px 380px; animation: drift 90s linear infinite; opacity:.55; }}
.stApp::after {{ background-size: 560px 560px; animation-duration: 140s; animation-direction: reverse; opacity:.35; }}
@keyframes drift {{ from {{ transform: translate3d(0,0,0); }} to {{ transform: translate3d(-380px,-380px,0); }} }}

/* bordes redondeados y superficies */
[data-testid="stVerticalBlockBorderWrapper"] {{ border-radius: 22px !important; border: 1px solid var(--border) !important;
  background: linear-gradient(160deg, rgba(31,41,80,.85), rgba(23,31,58,.85)); backdrop-filter: blur(6px);
  transition: transform .25s ease, box-shadow .25s ease; }}
[data-testid="stVerticalBlockBorderWrapper"]:hover {{ transform: translateY(-2px); box-shadow: 0 10px 30px rgba(0,0,0,.35); }}
.stButton > button, .stDownloadButton > button, [data-testid="stPopover"] button {{ border-radius: 999px !important;
  border: 1px solid var(--border) !important; background: var(--surface2) !important; color: var(--text) !important;
  transition: all .2s ease; }}
.stButton > button:hover {{ border-color: var(--accent) !important; color: var(--accent) !important; }}
.stButton > button[kind="primary"] {{ background: linear-gradient(90deg, #5eead4, #60a5fa) !important; color: var(--ink) !important;
  border: none !important; font-weight: 800; }}
[data-testid="stTabs"] button[role="tab"] {{ border-radius: 999px; padding: 6px 14px; }}
[data-testid="stDataFrame"], [data-testid="stAlert"], [data-testid="stExpander"] {{ border-radius: 18px; overflow: hidden; }}
[data-testid="stMetric"] {{ background: rgba(255,255,255,.03); border-radius: 16px; padding: 10px 14px; }}
iframe {{ border-radius: 18px; }}

/* navegacion superior */
.st-key-nav [data-testid="stButtonGroup"] {{ background: rgba(23,31,58,.8); border: 1px solid var(--border);
  border-radius: 999px; padding: 6px; display: flex; flex-wrap: wrap; gap: 4px; }}
.st-key-nav [data-testid="stButtonGroup"] > div {{ flex-wrap: wrap !important; overflow: visible !important; gap: 4px; }}
.st-key-nav button {{ border-radius: 999px !important; border: none !important; }}

/* componentes propios */
.hero {{ position: relative; border-radius: 26px; overflow: hidden; padding: 22px 26px 30px 26px; margin-bottom: 14px;
  background: linear-gradient(120deg, rgba(37,99,235,.35), rgba(94,234,212,.18) 60%, rgba(196,161,255,.22));
  border: 1px solid var(--border); }}
.hero h1 {{ margin: 0; font-size: 1.9rem; font-weight: 900; display:flex; align-items:center; gap:12px; }}
.hero p {{ margin: 4px 0 0 0; color: var(--muted); }}
.hero svg.waves {{ position:absolute; left:0; bottom:-2px; width:200%; height:40px; animation: wave 12s linear infinite; }}
@keyframes wave {{ from {{ transform: translateX(0); }} to {{ transform: translateX(-50%); }} }}
.kpi {{ border-radius: 22px; padding: 16px 18px; background: var(--surface); border: 1px solid var(--border);
  display:flex; align-items:center; gap:14px; animation: rise .6s ease; }}
.kpi .n {{ font-size: 1.9rem; font-weight: 900; line-height: 1; }}
.kpi .t {{ color: var(--muted); font-size: .85rem; margin-top: 4px; }}
.kpi .ic {{ width:46px; height:46px; border-radius: 16px; display:flex; align-items:center; justify-content:center; flex-shrink:0; }}
@keyframes rise {{ from {{ opacity:0; transform: translateY(8px); }} to {{ opacity:1; transform: none; }} }}
.pill {{ display:inline-flex; align-items:center; gap:8px; padding:6px 14px; border-radius:999px; font-weight:800;
  color: var(--ink); font-size: .95rem; }}
.pill.big {{ font-size: 1.35rem; padding: 10px 22px; }}
.chip {{ display:inline-flex; align-items:center; gap:6px; padding:3px 10px; border-radius:999px; font-size:.8rem;
  background: rgba(255,255,255,.06); color: var(--muted); margin: 2px 4px 2px 0; }}
.h {{ display:flex; align-items:center; gap:10px; margin:.3rem 0 .6rem 0; font-weight:800; }}
.h.h2 {{ font-size:1.45rem; }} .h.h3 {{ font-size:1.12rem; }}
.muted {{ color: var(--muted); font-size:.88rem; }}
.why {{ border-radius: 16px; background: rgba(255,209,102,.08); border: 1px solid rgba(255,209,102,.35); padding: 10px 16px; margin: 6px 0 10px 0; }}
.why ul {{ margin: 4px 0 0 0; padding-left: 18px; }}
.test {{ display:flex; align-items:flex-start; gap:10px; margin:.4rem 0; }}
.legend {{ display:flex; flex-wrap:wrap; gap:14px; align-items:center; font-size:.95rem; margin:8px 0 2px 0; }}
.bar {{ height: 12px; border-radius: 999px; background: rgba(255,255,255,.07); overflow: hidden; }}
.bar > span {{ display:block; height:100%; border-radius:999px; transform-origin:left; animation: grow 1.1s cubic-bezier(.2,.8,.2,1); }}
@keyframes grow {{ from {{ transform: scaleX(0); }} to {{ transform: scaleX(1); }} }}

/* animaciones SVG: trazos que se dibujan, anillos que se llenan, pulsos. Sin fill-mode: si el navegador
   no anima (pestana en segundo plano, ahorro de energia), se ve el estado final normal. */
.draw {{ stroke-dasharray: 100; stroke-dashoffset: 0; animation: draw 1.6s ease; }}
@keyframes draw {{ from {{ stroke-dashoffset: 100; }} }}
.ring-fill {{ animation: ring 1.4s cubic-bezier(.2,.8,.2,1); }}
@keyframes ring {{ from {{ stroke-dasharray: 0 100; }} }}
.pulse {{ transform-origin: center; animation: pulse 2s ease-out infinite; }}
@keyframes pulse {{ 0% {{ transform: scale(.6); opacity:.9; }} 100% {{ transform: scale(1.9); opacity:0; }} }}
.float {{ animation: float 4s ease-in-out infinite; }}
@keyframes float {{ 0%,100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-4px); }} }}
@media (max-width: 640px) {{ .hero h1 {{ font-size: 1.4rem; }} .kpi .n {{ font-size: 1.5rem; }} .block-container {{ padding-top: 3rem; }} }}
</style>
"""


def apply() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    _altair_theme()


def _altair_theme() -> None:
    @alt.theme.register("deteccion", enable=True)
    def _t():
        return alt.theme.ThemeConfig({"config": {
            "background": "transparent", "view": {"stroke": "transparent"},
            "axis": {"labelColor": MUTED, "titleColor": MUTED, "gridColor": "rgba(255,255,255,0.07)",
                     "domainColor": "rgba(255,255,255,0.15)", "tickColor": "rgba(255,255,255,0.15)"},
            "legend": {"labelColor": TEXT, "titleColor": MUTED},
            "title": {"color": TEXT}, "bar": {"cornerRadiusEnd": 6}}})
