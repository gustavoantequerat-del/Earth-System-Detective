"""Mapa 3D (relieve real) y comparador antes/despues del Detector de huella humana."""
from __future__ import annotations

import base64
import io
import math
import os
import urllib.request
from functools import lru_cache
from pathlib import Path

import pydeck as pdk

TERRAIN = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"  # AWS Terrain Tiles, sin clave
ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
PLACE_COLORS = {"Mina o cantera": [255, 23, 68], "Industria": [255, 145, 0],
                "Ciudad o pueblo": [213, 0, 249], "Represa o canal": [0, 229, 255]}
def plain(text: str) -> str:
    """Sin tildes ni enie: la capa de texto del mapa solo dibuja letras basicas."""
    import unicodedata
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
DECODER = {"rScaler": 256, "gScaler": 1, "bScaler": 1 / 256, "offset": -32768}


@lru_cache(maxsize=256)
def elevation(lat: float, lon: float, z: int = 10) -> float:
    """Altura del terreno en metros (para que las columnas no queden enterradas en el Altiplano)."""
    try:
        from PIL import Image
        n = 2 ** z
        xf = (lon + 180) / 360 * n
        yf = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
        url = TERRAIN.format(z=z, x=int(xf), y=int(yf))
        with urllib.request.urlopen(url, timeout=10) as r:
            img = Image.open(io.BytesIO(r.read())).convert("RGB")
        px = img.getpixel((int((xf % 1) * 256), int((yf % 1) * 256)))
        return px[0] * 256 + px[1] + px[2] / 256 - 32768
    except Exception:
        return 0.0


# ------------------------------------------------------------------ Earth Engine en vivo
_EE_OK: bool | None = None


def _service_account() -> dict | None:
    try:
        import streamlit as st
        if "gee_service_account" in st.secrets:
            return dict(st.secrets["gee_service_account"])
    except Exception:  # sin archivo de secretos
        pass
    return None


def ee_ready() -> bool:
    global _EE_OK
    if _EE_OK is None:
        try:
            import ee
            import json
            cfg = Path(__file__).resolve().parent.parent / "config" / "settings.json"
            project = os.environ.get("UMA_GEE_PROJECT") or (
                json.loads(cfg.read_text(encoding="utf-8")).get("gee_project") if cfg.exists() else None)
            key = _service_account()
            if key:  # publicacion web: cuenta de servicio guardada en los secretos de Streamlit
                creds = ee.ServiceAccountCredentials(key["client_email"], key_data=json.dumps(key))
                ee.Initialize(creds, project=project or key.get("project_id"))
            else:    # computadora con `earthengine authenticate`
                ee.Initialize(project=project)
            ee.Number(1).getInfo()  # confirma que la conexion funciona
            _EE_OK = True
        except Exception:
            _EE_OK = False
    return _EE_OK


NATURAL_HEX = "1e40af"      # agua natural: azul profundo (theme.NATURAL)
ARTIFICIAL_HEX = "22e5ff"   # agua artificial: celeste neon (theme.ARTIFICIAL)
NATURAL_RGB = [30, 64, 175]
ARTIFICIAL_RGB = [34, 229, 255]


_TILE_CACHE: dict = {}
TILE_TTL_S = 2 * 3600


def live_texture(year: int, mode: str = "landsat", fires: bool = False, day: str = "") -> str | None:
    """Direccion de teselas de Earth Engine, guardada 2 horas (las direcciones expiran despues)."""
    import time
    key = (year, mode, fires, day)
    hit = _TILE_CACHE.get(key)
    if hit and time.time() - hit[0] < TILE_TTL_S:
        return hit[1]
    url = _live_texture(year, mode, fires, day)
    if url:
        _TILE_CACHE[key] = (time.time(), url)
    return url


def _live_texture(year: int, mode: str = "landsat", fires: bool = False, day: str = "") -> str | None:
    """Teselas de Earth Engine para pintar sobre el relieve.

    mode "agua": relieve sombreado (NASADEM) con el agua de MapBiomas Agua del ano: natural en azul oscuro,
                 artificial (represas, estanques, pozas mineras) en celeste neon.
    mode "landsat": Landsat de epoca seca del ano con el agua natural y artificial encima.
    fires: focos de calor NASA FIRMS de los ultimos 7 dias. `day` solo invalida la cache.
    """
    if not ee_ready():
        return None
    import ee
    from uma.gee_extract import MB_WATER, landsat_dry, landsat_vis
    bolivia = ee.Geometry.Rectangle([-70.5, -23.5, -57.0, -9.5])
    if mode == "reciente":
        end = ee.Date(day) if day else ee.Date(0)

        def clear(i):  # quita nubes, sombras y cirros con la clasificacion de escena de Sentinel-2
            scl = i.select("SCL")
            return i.updateMask(scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)))
        s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(bolivia)
              .filterDate(end.advance(-90, "day"), end.advance(1, "day"))
              .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 40)).map(clear).median())
        img = s2.select(["B4", "B3", "B2"]).visualize(min=0, max=3000, gamma=1.2)
        country = (ee.FeatureCollection("FAO/GAUL/2015/level0").filter(ee.Filter.eq("ADM0_NAME", "Bolivia"))
                   .geometry().simplify(2000).buffer(15000))
        return img.clip(country).getMapId()["tile_fetcher"].url_format
    if mode == "agua":
        dem = ee.Image("NASA/NASADEM_HGT/001").select("elevation")
        img = ee.Terrain.hillshade(dem).visualize(min=60, max=255, palette=["1b1f24", "8a929c"])
    else:
        img = landsat_vis(landsat_dry(min(year, 2024), bolivia))
    cls = ee.Image(MB_WATER).select(f"classification_{min(max(year, 1985), 2025)}")
    natural = cls.gte(11).And(cls.lte(14)).selfMask()
    artificial = cls.gte(21).And(cls.lte(24)).selfMask()  # de lejos se ve con la capa de puntos neon
    img = img.blend(natural.visualize(palette=[NATURAL_HEX], opacity=0.95))
    img = img.blend(artificial.visualize(palette=[ARTIFICIAL_HEX]))
    # solo Bolivia (con 15 km de margen): el resto queda transparente y Bolivia resalta sobre el fondo oscuro
    country = (ee.FeatureCollection("FAO/GAUL/2015/level0").filter(ee.Filter.eq("ADM0_NAME", "Bolivia"))
               .geometry().simplify(2000).buffer(15000))
    img = img.clip(country)
    if fires:
        now = ee.Date(day or ee.Date(0))
        firms = ee.ImageCollection("FIRMS").filterDate(now.advance(-7, "day"), now.advance(1, "day")).select("T21").max()
        img = img.blend(firms.gt(0).selfMask().focalMax(2).visualize(palette=["ff3d00"]))
    return img.getMapId()["tile_fetcher"].url_format


# ------------------------------------------------------------------ deck
CARTO_DARK_STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"


def build_deck(rows: list[dict], selected: dict | None, texture: str | None, places: list | None = None,
               national: list | None = None, artificial: list | None = None, height_scale: float = 1.0,
               mode3d: bool = True) -> pdk.Deck:
    """rows: dicts con name, lat, lon, state, color, change, loss (perdida %, >= 0)."""
    for r in rows:
        r["z"] = elevation(round(r["lat"], 3), round(r["lon"], 3)) if mode3d else 0
        r["halo"] = list(r["color"]) + [70]
        r["label"] = plain(r.get("label", r["name"]))
    if not mode3d:  # 2D: todo al nivel del suelo, sin descargar relieve
        for r in rows:
            r["z"] = 0
        for coll in (national or [], artificial or []):
            for x in coll:
                x["z"] = 0
    layers = []
    if mode3d:
        layers.append(pdk.Layer("TerrainLayer", id="relieve", elevation_decoder=DECODER, elevation_data=TERRAIN,
                                texture=texture, max_zoom=13, strategy="no-overlap", mesh_max_error=6))
    if artificial:  # agua artificial de todo el pais: brillo + punto, en celeste neon
        layers.append(pdk.Layer("ScatterplotLayer", id="artificial_brillo", data=artificial,
                                get_position="[lon, lat, z]", get_fill_color=ARTIFICIAL_RGB + [60],
                                get_radius="r_glow", radius_min_pixels=4, radius_max_pixels=40, pickable=False))
        layers.append(pdk.Layer("ScatterplotLayer", id="artificial", data=artificial, get_position="[lon, lat, z]",
                                get_fill_color=ARTIFICIAL_RGB, get_radius="r", radius_min_pixels=2,
                                radius_max_pixels=14, pickable=True))
    if national:
        layers.append(pdk.Layer("ScatterplotLayer", id="nacional", data=national, get_position="[lon, lat, z]",
                                get_fill_color="color", get_radius="radius", radius_min_pixels=5, radius_max_pixels=30,
                                opacity=0.95, pickable=True, stroked=True, get_line_color=[255, 255, 255],
                                line_width_min_pixels=1.5))
    # halo de color alrededor de cada cuerpo de agua analizado: la senal se ve desde lejos
    layers.append(pdk.Layer("ScatterplotLayer", id="halo", data=rows, get_position="[lon, lat, z]",
                            get_fill_color="halo", get_line_color="color", get_radius=6000 if selected else 30000,
                            radius_min_pixels=26, stroked=True, line_width_min_pixels=4, pickable=False))
    layers.append(pdk.Layer("ColumnLayer", id="cuerpos", data=rows, get_position="[lon, lat, z]",
                            get_elevation="loss", elevation_scale=(15 if selected else 900) * height_scale,
                            radius=400 if selected else 14000, get_fill_color="color", get_line_color=[255, 255, 255],
                            pickable=True, auto_highlight=True, extruded=True))
    layers.append(pdk.Layer("TextLayer", id="etiquetas", data=rows, get_position="[lon, lat, z]", get_text="label",
                            get_size=16, get_color=[255, 255, 255], get_pixel_offset=[0, -26], background=True,
                            get_background_color=[10, 10, 10, 200], font_weight=700, billboard=True))
    if selected and places:
        # mismos campos que las columnas para que el tooltip sirva a todas las capas
        pts = [dict(pl, z=elevation(round(pl["lat"], 3), round(pl["lon"], 3)) + 150,
                    color=PLACE_COLORS.get(pl["kind"], [255, 255, 255]),
                    name=plain(pl["name"]) or "(sin nombre)", state=pl["kind"], change=f"a {pl['dist_km']} km")
                for pl in places[:30]]
        layers.append(pdk.Layer("ScatterplotLayer", id="lugares", data=pts, get_position="[lon, lat, z]",
                                get_fill_color="color", get_radius=400, radius_min_pixels=7, pickable=True,
                                stroked=True, get_line_color=[255, 255, 255], line_width_min_pixels=2))
        layers.append(pdk.Layer("TextLayer", id="nombres", data=[x for x in pts if x["name"] != "(sin nombre)"],
                                get_position="[lon, lat, z]", get_text="name", get_size=13, get_color=[255, 255, 255],
                                get_pixel_offset=[0, -16], background=True, get_background_color=[0, 0, 0, 170]))
    pitch = (60 if selected else 40) if mode3d else 0
    if selected:
        view = pdk.ViewState(latitude=selected["lat"], longitude=selected["lon"], zoom=9.3, pitch=pitch,
                             bearing=-20 if mode3d else 0)
    else:
        view = pdk.ViewState(latitude=-16.6, longitude=-64.6, zoom=5.4, pitch=pitch, bearing=0)
    return pdk.Deck(layers=layers, initial_view_state=view, map_style=None if mode3d else CARTO_DARK_STYLE,
                    tooltip={"html": "<b>{name}</b><br/>{state} · {change}",
                             "style": {"backgroundColor": "#111", "color": "white", "fontSize": "14px"}})


# ------------------------------------------------------------------ antes / despues
def _b64(p: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


def before_after_html(before: Path, after: Path, label_a: str, label_b: str,
                      water_a: Path | None = None, water_b: Path | None = None, height: int = 520,
                      changes: Path | None = None, legend: dict | None = None) -> str:
    """Comparador con deslizador: a la izquierda 'antes', a la derecha 'despues'.

    water_*: mascara de agua opcional por lado. changes: capa transparente de lo que aparecio
    (se muestra sobre el 'despues'), con su leyenda {clave: {color, label, ha}}.
    """
    def layer(img, water, extra=""):
        w = f"<img src='{_b64(water)}' class='w'>" if water and water.exists() else ""
        return f"<img src='{_b64(img)}'>{w}{extra}"
    chg = f"<img src='{_b64(changes)}' class='c'>" if changes and changes.exists() else ""
    leg = ""
    if chg and legend:
        items = "".join(f"<span><i style='background:{v['color']}'></i>{v['label']}"
                        f"{' · ' + format(v['ha'], ',') + ' ha' if v.get('ha') else ''}</span>"
                        for v in legend.values())
        leg = (f"<label class='tog'><input type='checkbox' id='chkc' checked> Mostrar que aparecio alrededor</label>"
               f"<div class='leg'>{items}<span><i style='background:#ffffff'></i>Laguna analizada</span></div>")
    return f"""
<style>
.ba{{position:relative;width:100%;height:{height}px;overflow:hidden;border-radius:8px;background:#111;
     font-family:sans-serif;user-select:none}}
.ba .pane{{position:absolute;inset:0}}
.ba img{{position:absolute;inset:0;width:100%;height:100%;object-fit:contain}}
.ba img.w{{opacity:0;transition:opacity .2s}}
.ba.showw img.w{{opacity:.6}}
.ba img.c{{opacity:0;transition:opacity .2s}}
.ba.showc img.c{{opacity:.85}}
.leg{{font-family:sans-serif;color:#ddd;font-size:13px;display:flex;flex-wrap:wrap;gap:12px;margin-top:4px}}
.leg i{{display:inline-block;width:12px;height:12px;border-radius:2px;margin-right:5px;vertical-align:-1px}}
.ba .after{{clip-path:inset(0 0 0 50%)}}
.ba .bar{{position:absolute;top:0;bottom:0;left:50%;width:3px;background:#fff;box-shadow:0 0 6px #000}}
.ba .tag{{position:absolute;top:10px;padding:4px 10px;border-radius:4px;background:rgba(0,0,0,.65);color:#fff;font-size:14px}}
.ba input[type=range]{{position:absolute;inset:0;width:100%;height:100%;opacity:0;cursor:ew-resize;margin:0}}
.tog{{font-family:sans-serif;color:#ccc;font-size:13px;margin-top:6px}}
</style>
<div class="ba{' showc' if chg else ''}" id="ba">
  <div class="pane">{layer(before, water_a)}</div>
  <div class="pane after" id="after">{layer(after, water_b, chg)}</div>
  <div class="bar" id="bar"></div>
  <div class="tag" style="left:10px">Antes · {label_a}</div>
  <div class="tag" style="right:10px">Despues · {label_b}</div>
  <input type="range" min="0" max="100" value="50" id="rng">
</div>
{'' if chg else '<label class="tog"><input type="checkbox" id="chk"> Marcar el agua detectada (JRC)</label>'}
{leg}
<script>
const r=document.getElementById('rng'),a=document.getElementById('after'),b=document.getElementById('bar');
r.addEventListener('input',()=>{{a.style.clipPath=`inset(0 0 0 ${{r.value}}%)`;b.style.left=r.value+'%';}});
const c1=document.getElementById('chk'); if(c1) c1.addEventListener('change',e=>document.getElementById('ba').classList.toggle('showw',e.target.checked));
const c2=document.getElementById('chkc'); if(c2) c2.addEventListener('change',e=>document.getElementById('ba').classList.toggle('showc',e.target.checked));
</script>"""
