"""Cerca de mi: que fuentes de agua cercanas estan afectadas, con su estado, alertas y proteccion legal."""
from __future__ import annotations

import pandas as pd
import pydeck as pdk
import streamlit as st

import data
import icons as ic
import map3d
import nav
import theme as th
import ui

# Boton que pide la ubicacion al navegador y la pasa a la app por la URL. La ubicacion no se guarda en ningun lado.
GEO_BUTTON = """
<div style="font-family:sans-serif;margin:0">
<button id="b" style="border:none;border-radius:999px;padding:10px 18px;font-weight:800;cursor:pointer;
  background:linear-gradient(90deg,#5eead4,#60a5fa);color:#121528;font-size:15px;white-space:nowrap">Usar mi ubicacion</button>
<div id="m" style="color:#a3abc9;margin-top:6px;font-size:12px"></div></div>
<style>body{margin:0;overflow:hidden}</style>
<script>
document.getElementById('b').onclick = () => {
  const m = document.getElementById('m');
  if (!navigator.geolocation) { m.textContent = 'Este navegador no permite ubicacion.'; return; }
  m.textContent = 'Pidiendo permiso...';
  navigator.geolocation.getCurrentPosition(p => {
    const u = new URL(window.parent.location.href);
    u.searchParams.set('lat', p.coords.latitude.toFixed(4));
    u.searchParams.set('lon', p.coords.longitude.toFixed(4));
    u.searchParams.set('vista', 'cerca');
    window.parent.location.href = u.toString();
  }, e => { m.textContent = 'No se pudo obtener la ubicacion (' + e.message + ').'; },
  {enableHighAccuracy: false, timeout: 15000});
};
</script>
"""


def _where() -> tuple[float, float, str] | None:
    qp = st.query_params
    if "lat" in qp and "lon" in qp:
        try:
            return float(qp["lat"]), float(qp["lon"]), "tu ubicacion"
        except ValueError:
            pass
    return None


def render(results: list[dict], national: list[dict], by_id: dict) -> None:
    ui.md(ui.heading("crosshair", "Cerca de mi: fuentes de agua afectadas"))
    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 3, 2], gap="medium")
        with c1:
            st.iframe(GEO_BUTTON, height=78)
        with c2:
            place = st.text_input("O busca un lugar", placeholder="Ej.: Oruro, San Ignacio de Velasco, Copacabana",
                                  label_visibility="collapsed")
        with c3:
            radius = st.slider("Radio (km)", 10, 200, 60, step=10, label_visibility="collapsed",
                               help="Radio de busqueda en km")
        st.caption("La ubicacion se usa solo en tu navegador para esta consulta y no se guarda. La busqueda por nombre "
                   "consulta OpenStreetMap con el texto escrito.")
    where = None
    if place:
        g = data.geocode(place)
        if g:
            where = (g["lat"], g["lon"], g["name"].split(",")[0])
        else:
            st.warning("No encontre ese lugar en Bolivia.")
    where = where or _where()
    if not where:
        st.info("Usa tu ubicacion o busca un lugar para ver las fuentes de agua cercanas.")
        return
    lat, lon, label = where

    near = []
    for r in results + national:
        d = data.distance_km(lat, lon, r["lat"], r["lon"])
        if d <= radius:
            near.append({**r, "dist": d, "full": r["body_id"] in by_id})
    near.sort(key=lambda r: (th.SEVERITY[r["state"]], r["dist"]))
    art = data.artificial_points()
    art_near = [a for a in (art or {}).get("points", []) if data.distance_km(lat, lon, a["lat"], a["lon"]) <= radius]
    affected = [r for r in near if r["state"] in ("Huella humana", "Alerta temprana", "Incalculable", "Aguas arriba")]
    fires = [f for f in ((data.weekly() or {}).get("rows", [])) if f["alerta"] and any(
        n["body_id"] == f["body_id"] for n in near)]

    cols = st.columns(4)
    kp = [("map-pin", label[:22], "Centro de la busqueda", th.ACCENT_2),
          ("droplets", str(len(near)), f"Fuentes de agua a {radius} km", th.ACCENT),
          ("triangle-alert", str(len(affected)), "Afectadas o en alerta", th.state_color("Huella humana")),
          ("factory", f"{len(art_near):,}", "Represas, estanques y pozas", th.ARTIFICIAL)]
    for col, (icon, v, t, c) in zip(cols, kp):
        with col:
            ui.md(ui.kpi(icon, v, t, c))
    if fires:
        st.error(f"Alerta de incendio esta semana en: {', '.join(f['name'] for f in fires)}")

    _mini_map(lat, lon, radius, near, art_near)
    if not near:
        st.info("No hay cuerpos de agua analizados en ese radio. Prueba con un radio mayor.")
        return
    ui.md(ui.heading("list", "Lo que hay cerca, de lo mas grave a lo menos", 3))
    for start in range(0, min(len(near), 24), 3):
        cols = st.columns(3, gap="medium")
        for col, r in zip(cols, near[start:start + 3]):
            with col, st.container(border=True):
                prot = data.protection(r["body_id"])
                badges = ui.chip(f"{r['dist']:.0f} km", "map-pin")
                if prot["ramsar"]:
                    badges += ui.chip(f"Ramsar: {prot['ramsar']}", "shield-check", "#5ee6a8")
                elif prot["areas"]:
                    badges += ui.chip("Area protegida", "shield-check", "#5ee6a8")
                ui.md(f"<div style='font-weight:800'>{r['name'].split(' (')[0]}</div>"
                      f"<div style='margin:6px 0'>{ui.pill(r['state'])}</div>"
                      f"<div style='font-size:1.4rem;font-weight:900;color:{th.state_color(r['state'])}'>"
                      f"{r['trend']['change_pct']:+.0f}%</div>{badges}")
                if r["full"]:
                    nav.open_button(r["body_id"], f"near_{r['body_id']}")
                else:
                    ui.md("<div class='muted'>Barrido nacional (diagnostico rapido)</div>")
    if len(near) > 24:
        st.caption(f"Se muestran 24 de {len(near)}. Reduce el radio para ver las mas cercanas.")


def _mini_map(lat, lon, radius, near, art_near) -> None:
    pts = pd.DataFrame([{"lon": r["lon"], "lat": r["lat"], "name": r["name"], "state": r["state"],
                         "change": f"{r['trend']['change_pct']:+.0f}% · {r['dist']:.0f} km",
                         "color": th.state_rgb(r["state"]), "radius": 2500 if r["full"] else 1200} for r in near])
    layers = [
        pdk.Layer("ScatterplotLayer", data=[{"lon": lon, "lat": lat}], get_position="[lon, lat]",
                  get_radius=radius * 1000, filled=True, get_fill_color=[94, 234, 212, 18], stroked=True,
                  get_line_color=[94, 234, 212, 200], line_width_min_pixels=2),
        pdk.Layer("ScatterplotLayer", data=[{"lon": a["lon"], "lat": a["lat"], "name": a["tipo"],
                                             "state": "Agua artificial", "change": f"{a['ha']:,.0f} ha"}
                                            for a in art_near],
                  get_position="[lon, lat]", get_radius=400, radius_min_pixels=2, get_fill_color=map3d.ARTIFICIAL_RGB,
                  pickable=True),
        pdk.Layer("ScatterplotLayer", data=pts, get_position="[lon, lat]", get_radius="radius", radius_min_pixels=6,
                  get_fill_color="color", stroked=True, get_line_color=[255, 255, 255], line_width_min_pixels=1.5,
                  pickable=True),
        pdk.Layer("ScatterplotLayer", data=[{"lon": lon, "lat": lat, "name": "Centro de la busqueda", "state": "",
                                             "change": ""}],
                  get_position="[lon, lat]", get_radius=600, radius_min_pixels=7, get_fill_color=[255, 255, 255],
                  pickable=True),
    ]
    zoom = 9.5 if radius <= 30 else 8.3 if radius <= 80 else 7
    deck = pdk.Deck(layers=layers, initial_view_state=pdk.ViewState(latitude=lat, longitude=lon, zoom=zoom),
                    map_style=map3d.CARTO_DARK_STYLE, tooltip={"html": "<b>{name}</b><br/>{state} {change}",
                                             "style": {"backgroundColor": "#171f3a", "color": "white"}})
    st.pydeck_chart(deck, height=420)
    ui.md("<div class='legend'>" + "".join(
        f"<span class='chip' style='color:{v['color']}'>{ic.svg(v['icon'], v['color'], 14, 2.4)}{s}</span>"
        for s, v in th.STATES.items()) + f"<span class='chip' style='color:{th.ARTIFICIAL}'>Agua artificial</span></div>")
