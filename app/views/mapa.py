"""Mapa 3D de alertas: relieve, agua natural y artificial, columnas por cuerpo de agua y ficha rapida."""
from __future__ import annotations

import datetime

import streamlit as st

import data
import icons as ic
import map3d
import nav
import theme as th
import ui


def _zguess(lat: float, lon: float) -> int:
    """Altura aproximada para que los puntos no queden bajo el relieve."""
    return 4300 if lon < -65.6 and lat < -14.5 else 700


def _layers_menu(national: list[dict], art: dict | None):
    live_ok = map3d.ee_ready()
    with st.popover("Capas del mapa", width="content"):
        view3d = st.segmented_control("Vista", ["3D con relieve", "2D rapido"], default="3D con relieve",
                                      key="map_dim") != "2D rapido"
        modes = (["Agua natural y artificial", "Imagen mas reciente (Sentinel-2)", "Landsat + agua"]
                 if live_ok else []) + ["Satelite (Esri)"]
        mode = st.radio("Fondo", modes, disabled=not view3d,
                        help="En 2D se usa un mapa base oscuro liviano, ideal para celular.")
        year = st.slider("Ano", 1985, 2025, 2024, disabled=not view3d or not mode.startswith(("Agua", "Landsat")))
        fires = st.toggle("Focos de calor NASA FIRMS (7 dias)", False, disabled=not live_ok, key="chk_fires")
        show_art = st.toggle("Puntos de agua artificial", art is not None, disabled=art is None, key="chk_art")
        show_nat = st.toggle(f"Barrido nacional ({len(national)})", bool(national), disabled=not national, key="chk_nat")
        if not live_ok:
            st.caption("Earth Engine no esta autenticado: solo la imagen satelital de fondo.")
    return mode, year, fires, show_art, show_nat, view3d


def render(visible: list[dict], by_id: dict, national: list[dict]) -> None:
    art = data.artificial_points()
    head, menu = st.columns([4, 1])
    with head:
        ui.md(ui.heading("map", "Mapa de alertas"))
    with menu:
        mode, year, fires, show_art, show_nat, view3d = _layers_menu(national, art)

    texture = map3d.ESRI
    if view3d and mode != "Satelite (Esri)":
        kind = "agua" if mode.startswith("Agua") else "reciente" if mode.startswith("Imagen") else "landsat"
        with st.spinner("Generando la capa en Earth Engine..."):
            texture = map3d.live_texture(year, kind, fires, datetime.date.today().isoformat()) or map3d.ESRI

    rows = [{"body_id": r["body_id"], "name": r["name"], "label": r["name"].split(" (")[0], "lat": r["lat"],
             "lon": r["lon"], "state": r["state"], "color": th.state_rgb(r["state"]),
             "change": f"{r['trend']['change_pct']:+.0f}%", "loss": max(0.0, -r["trend"]["change_pct"]) + 5}
            for r in visible]
    nat_rows = [{"name": f"{n['name']} · barrido nacional · {n.get('ha', 0):,} ha", "lat": n["lat"], "lon": n["lon"],
                 "z": _zguess(n["lat"], n["lon"]), "state": n["state"], "change": f"{n['trend']['change_pct']:+.0f}%",
                 "color": th.state_rgb(n["state"]), "radius": 1500 + 60 * (n.get("ha", 0) ** 0.5)}
                for n in national] if show_nat else []
    art_rows = []
    if art and show_art:
        for a in art["points"]:
            r_m = max((a["ha"] * 1e4 / 3.1416) ** 0.5, 250)
            art_rows.append({"name": f"{a['tipo']} · {a['ha']:,.0f} ha", "state": "Agua artificial",
                             "change": f"MapBiomas Agua {art['year']}", "lat": a["lat"], "lon": a["lon"],
                             "z": _zguess(a["lat"], a["lon"]), "r": r_m, "r_glow": r_m * 4})

    current = by_id.get(st.session_state.sel)
    deck = map3d.build_deck(rows, current, texture, data.places(st.session_state.sel), nat_rows, art_rows,
                            mode3d=view3d)
    event = st.pydeck_chart(deck, on_select="rerun", selection_mode="single-object", key="map3d", height=640)
    picked = (event.selection.get("objects", {}) or {}).get("cuerpos") if event else None
    if picked and picked[0]["body_id"] != st.session_state.sel:
        st.session_state.sel = picked[0]["body_id"]
        st.rerun()

    legend = "".join(f"<span class='chip' style='color:{v['color']}'>{ic.svg(v['icon'], v['color'], 15, 2.4)}{s}</span>"
                     for s, v in th.STATES.items())
    legend += (f"<span class='chip' style='color:#{map3d.NATURAL_HEX}'>{ic.svg('waves', '#5b8cff', 15, 2.4)}"
               "Agua natural</span>"
               f"<span class='chip' style='color:#{map3d.ARTIFICIAL_HEX}'>{ic.svg('droplets', '#' + map3d.ARTIFICIAL_HEX, 15, 2.4)}"
               "Agua artificial</span>")
    ui.md(f"<div class='legend'>{legend}</div><div class='muted'>Columnas: analisis completo (altura = % de agua "
          "perdida). Puntos con borde blanco: barrido nacional. Clic en una columna para volar hasta ahi; "
          "Ctrl + arrastrar para girar.</div>")
    st.write("")
    left, right = st.columns([3, 2], gap="large")
    with left:
        _quick_card(current)
    with right, st.container(border=True):
        ui.md(ui.heading("siren", "Donde actuar primero", 3, th.state_color("Huella humana")))
        for r in sorted(visible, key=lambda r: (th.SEVERITY[r["state"]], r["trend"]["change_pct"])):
            if st.button(f"{r['name'].split(' (')[0]} · {r['trend']['change_pct']:+.0f}%", key=f"go_{r['body_id']}",
                         width="stretch"):
                st.session_state.sel = r["body_id"]
                st.rerun()


def _quick_card(r: dict | None) -> None:
    with st.container(border=True):
        if not r:
            ui.md(ui.heading("crosshair", "Elige un cuerpo de agua", 3) +
                  "<div class='muted'>Haz clic en una columna del mapa o en la lista de la derecha.</div>")
            return
        color = th.state_color(r["state"])
        top = next((s for s in r["suspects"] if not s.get("indirect")), None)
        ui.md(f"<div style='font-weight:900;font-size:1.3rem'>{r['name']}</div>"
              f"<div style='margin:8px 0'>{ui.pill(r['state'], big=True)}</div>")
        c1, c2, c3 = st.columns([2, 2, 3])
        c1.metric("Agua perdida", f"{r['trend']['change_pct']:+.0f}%")
        with c2:
            ui.md(ui.ring(r["n_pass"] / 3, color, f"{r['n_pass']}/3"))
        with c3:
            ui.md(ui.sparkline(r["observed"], color))
        if top:
            ui.md(ui.chip(f"{top['label']} · evidencia {top['evidence']}", "search"))
        if r.get("why"):
            ui.md("<div class='why'><ul>" + "".join(f"<li>{w}</li>" for w in r["why"][:3]) + "</ul></div>")
        b1, b2 = st.columns(2)
        if b1.button("Abrir ficha completa", type="primary", width="stretch", key="btn_open"):
            nav.go("Ficha", r["body_id"])
        if b2.button("Volver a Bolivia", width="stretch", key="btn_back"):
            st.session_state.sel = None
            st.rerun()
