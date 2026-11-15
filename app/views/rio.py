"""El rio por tramos (Desaguadero y Mauri): agua en el cauce, riego en epoca seca, represas y lo que hay en el camino."""
from __future__ import annotations

import altair as alt
import pandas as pd
import pydeck as pdk
import streamlit as st

import data
import map3d
import theme as th
import ui

FEEDS = {"uru_uru": ["T1", "T2", "T3", "T4", "T5", "M"], "poopo": ["T1", "T2", "T3", "T4", "T5", "T6", "M"]}
KIND_COLOR = {"Canal o acequia": [34, 229, 255], "Represa o toma": [96, 165, 250], "Reservorio": [96, 165, 250],
              "Mina o cantera": [255, 122, 122], "Planta de tratamiento": [94, 230, 168],
              "Piletas de sal": [255, 209, 102]}


def available(body_id: str) -> bool:
    return body_id in FEEDS and (data.DATA / "rio_tramos.csv").exists()


def _change(df: pd.DataFrame, var: str) -> pd.DataFrame:
    d = df[df["var"] == var].pivot(index="year", columns="reach", values="value")
    base, last = d.loc[1985:2000].mean(), d.iloc[-5:].mean()
    return pd.DataFrame({"base": base, "ultimos5": last, "cambio_pct": 100 * (last - base) / base.where(base > 0)})


def render(body_id: str) -> None:
    df = data.csv_file(data.DATA / "rio_tramos.csv")
    gj = data.json_file(data.DATA / "rio_tramos.geojson") or {"features": []}
    osm = data.json_file(data.DATA / "rio_osm.json") or []
    rids = FEEDS[body_id]
    meta = {f["properties"]["reach"]: f["properties"] for f in gj["features"]}
    df = df[df.reach.isin(rids)]
    water, green, art = _change(df, "water_ha"), _change(df, "green_ha"), _change(df, "artificial_ha")

    ui.md("<div class='muted'>El agua que llega a esta laguna baja por el Desaguadero desde el Titicaca (y el Mauri "
          "desde Peru). Aqui se mira el rio tramo a tramo: si el cauce pierde agua y al lado crece el verde en plena "
          "epoca seca, ese verde se riega con agua del rio.</div>")
    tot_g = green.loc[[r for r in rids if r in green.index]]
    g_base, g_last = tot_g["base"].sum(), tot_g["ultimos5"].sum()
    cols = st.columns(3)
    with cols[0]:
        ui.md(ui.kpi("droplets", f"{water['cambio_pct'].mean():+.0f}%", "Agua en el cauce (promedio de tramos, "
                     "1985-2000 vs ultimos 5 anos)", th.NATURAL))
    with cols[1]:
        ui.md(ui.kpi("trending-down", f"{g_last - g_base:+,.0f} ha", f"Verde en epoca seca junto al rio "
                     f"({g_base:,.0f} -> {g_last:,.0f} ha)", "#5ee6a8"))
    with cols[2]:
        n = {k: sum(1 for x in osm if x["kind"] == k and (x["reach"] in rids or x["lake"] == body_id))
             for k in KIND_COLOR}
        ui.md(ui.kpi("factory", f"{n['Canal o acequia']} · {n['Represa o toma']} · {n['Mina o cantera']}",
                     "Canales · tomas/represas · minas en OpenStreetMap", th.ARTIFICIAL))

    _map(gj, osm, rids, body_id, green)
    left, right = st.columns([3, 2], gap="large")
    with left, st.container(border=True):
        ui.md(ui.heading("chart-line", "Verde en epoca seca junto al rio, por tramo", 3))
        g = df[df["var"] == "green_ha"].copy()
        g["tramo"] = g.reach.map(lambda r: f"{r} {meta.get(r, {}).get('name', '')}")
        st.altair_chart(alt.Chart(g).mark_line(strokeWidth=2.2).encode(
            x=alt.X("year:O", title=None, axis=alt.Axis(values=list(range(1985, 2025, 5)))),
            y=alt.Y("value:Q", title="ha verdes en junio-octubre"),
            color=alt.Color("tramo:N", legend=alt.Legend(orient="bottom", columns=2, title=None))), width="stretch")
        st.caption("Landsat, mediana de junio a octubre, NDVI mayor a 0.3, franja de 5 km a cada lado del cauce. "
                   "Incluye bofedales naturales: lo que importa es cuanto crece.")
    with right, st.container(border=True):
        ui.md(ui.heading("list", "Tramo por tramo", 3))
        rows = []
        for r in rids:
            if r not in water.index:
                continue
            m = meta.get(r, {})
            rows.append({"Tramo": f"{r} {m.get('name', '')}",
                         "Agua cauce": f"{water.loc[r, 'cambio_pct']:+.0f}%",
                         "Verde seca": f"{green.loc[r, 'ultimos5'] - green.loc[r, 'base']:+,.0f} ha",
                         "Represas": f"{art.loc[r, 'ultimos5'] - art.loc[r, 'base']:+,.0f} ha",
                         "Uso consuntivo": f"{m.get('uso_consuntivo_pct', 0):.1f}%"})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption("Uso consuntivo: agua que se consume respecto del caudal, segun HydroSHEDS (Grill et al. 2019).")

    _diversion(df, rids, meta, osm)

    near = sorted([x for x in osm if x["reach"] in rids or x["lake"] == body_id],
                  key=lambda x: (x["kind"], min(x["dist_rio_km"], x["dist_lago_km"])))
    with st.expander(f"Lo que hay en el camino segun OpenStreetMap ({len(near)})"):
        if near:
            st.dataframe(pd.DataFrame(near)[["kind", "name", "reach", "dist_rio_km", "lake", "dist_lago_km", "osm"]]
                         .rename(columns={"kind": "Tipo", "name": "Nombre", "reach": "Tramo", "dist_rio_km": "Al rio (km)",
                                          "lake": "Laguna", "dist_lago_km": "A la laguna (km)", "osm": "Ver"}),
                         hide_index=True, width="stretch",
                         column_config={"Ver": st.column_config.LinkColumn(display_text="ver")})
        else:
            st.caption("OpenStreetMap no registra canales, tomas ni minas en esta zona.")


def _map(gj: dict, osm: list, rids: list, body_id: str, green: pd.DataFrame) -> None:
    feats = []
    for f in gj["features"]:
        r = f["properties"]["reach"]
        if r not in rids:
            continue
        gr = green.loc[r, "ultimos5"] - green.loc[r, "base"] if r in green.index else 0
        color = [255, 122, 122] if gr > 500 else [255, 209, 102] if gr > 100 else [96, 165, 250]
        for line in f["geometry"]["coordinates"]:
            feats.append({"path": line, "name": f"{r} {f['properties']['name']}", "color": color,
                          "info": f"verde en seca {gr:+,.0f} ha"})
    pts = [{"lon": x["lon"], "lat": x["lat"], "name": x["name"] or x["kind"], "color": KIND_COLOR.get(x["kind"], [200, 200, 200]),
            "info": x["kind"]} for x in osm if x["reach"] in rids or x["lake"] == body_id]
    layers = [pdk.Layer("PathLayer", data=feats, get_path="path", get_color="color", width_min_pixels=4, pickable=True),
              pdk.Layer("ScatterplotLayer", data=pts, get_position="[lon, lat]", get_radius=500, radius_min_pixels=4,
                        get_fill_color="color", stroked=True, get_line_color=[255, 255, 255], line_width_min_pixels=1,
                        pickable=True)]
    deck = pdk.Deck(layers=layers, initial_view_state=pdk.ViewState(latitude=-17.7, longitude=-68.0, zoom=6.6),
                    map_style=map3d.CARTO_DARK_STYLE,
                    tooltip={"html": "<b>{name}</b><br/>{info}", "style": {"backgroundColor": "#171f3a", "color": "white"}})
    st.pydeck_chart(deck, height=430)
    ui.md("<div class='legend'><span class='chip' style='color:#ff7a7a'>Tramo con mucho riego nuevo (&gt;500 ha)</span>"
          "<span class='chip' style='color:#ffd166'>Algo de riego nuevo</span>"
          "<span class='chip' style='color:#60a5fa'>Sin cambio</span>"
          "<span class='chip' style='color:#22e5ff'>Canal o acequia</span>"
          "<span class='chip' style='color:#ff7a7a'>Mina</span></div>")


PAIRS = [("T1", "T2"), ("T2", "T3"), ("T3", "T4"), ("T4", "T5")]


def _diversion(df: pd.DataFrame, rids: list, meta: dict, osm: list) -> None:
    """Prueba de desvio: el tramo de abajo deberia tener agua en proporcion al de arriba. Si con los anos tiene
    menos de lo esperado (Mann-Kendall corregido) y al costado crece el verde en la seca o hay canales, alguien
    saca agua en ese tramo."""
    import numpy as np
    from scipy import stats

    from uma.monthly_model import modified_mk
    w = df[df["var"] == "water_ha"].pivot(index="year", columns="reach", values="value")
    g = df[df["var"] == "green_ha"].pivot(index="year", columns="reach", values="value").reindex(w.index)         .interpolate(limit_direction="both")
    rows = []
    for a, b in PAIRS:
        if a not in w or b not in w or b not in rids:
            continue
        base = w.loc[:2000]
        k = np.polyfit(base[a], base[b], 1)
        res = (w[b] - np.polyval(k, w[a])) / base[b].mean()
        mk = modified_mk(res.values)
        pct = stats.theilslopes(res.values, res.index)[0] * (res.index[-1] - res.index[0]) * 100
        canals = sum(1 for x in osm if x["reach"] == b and x["kind"] in ("Canal o acequia", "Represa o toma"))
        dg = g[b].iloc[-5:].mean() - g[b].loc[:2000].mean()
        sign = mk["p"] < 0.05 and pct < -10
        verdict = ("Posible desvio" if sign and (dg > 50 or canals) else "Pierde agua, sin senal de riego" if sign
                   else "Sin perdida significativa")
        rows.append({"Tramo": f"{a} -> {b} ({meta.get(b, {}).get('name', '')})", "Agua que no llega": f"{pct:+.0f}%",
                     "p (corregido)": f"{mk['p']:.3f}", "Verde en seca": f"{dg:+,.0f} ha", "Canales y tomas": canals,
                     "Resultado": verdict})
    if not rows:
        return
    with st.container(border=True):
        ui.md(ui.heading("search", "Se pierde agua en el camino? (prueba de desvio)", 3))
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption("Para cada tramo se predice su agua con la del tramo de arriba (1985-2000). Si despues llega cada vez "
                   "menos de lo esperado, y al costado crece el verde en plena epoca seca o hay canales, es la huella de "
                   "un desvio. Limite: se mide el ancho del agua en el cauce, no el caudal; un desvio chico puede no "
                   "notarse. El satelite SWOT (NASA/CNES, desde 2023) mide caudal y lo haria mas preciso.")
