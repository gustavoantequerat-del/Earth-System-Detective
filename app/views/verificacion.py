"""Como lo verificamos: datos contra fuentes independientes, veredictos contra lo publicado y limites del metodo."""
from __future__ import annotations

import sqlite3

import altair as alt
import pandas as pd
import streamlit as st

import data
import theme as th
import ui

OK, PART, BAD = "#5ee6a8", "#ffd166", "#ff7a7a"

# Veredicto vigente frente a estudios y prensa. Se revisa a mano cuando cambia el motor.
PUBLISHED = [
    ("concepcion", "Desmonte, agricultura comercial y desvio de un rio a un arrozal en 2003; seca en 2003-2007 y 2021.",
     [("Mongabay 2025", "https://es.mongabay.com/2025/10/bolivia-sitios-ramsar-amenazados/"),
      ("Ficha Ramsar", "https://rsis.ramsar.org/ris/1175")],
     "Coincide", "Misma causa (agricultura y ganaderia) y mismos anos de secado."),
    ("chiquitania_este", "Bolivia tuvo millones de hectareas quemadas en agosto-septiembre de 2019.",
     [("Los Tiempos", "https://www.lostiempos.com/node/471478")],
     "Coincide", "La vigilancia FIRMS aplicada a la semana del 2019-08-25 dispara la alerta (163 focos contra 1.2)."),
    ("poopo", "El clima solo no explica la desecacion de 2015: pesan el riego y el desvio del Desaguadero.",
     [("Satge et al. 2017", "https://www.mdpi.com/2072-4292/9/3/218")],
     "Coincide", "Aguas arriba: sigue al Titicaca (R2 0.73). El Desaguadero casi dejo de salir del lago (-98% de agua "
                 "en el cauce de salida) y el riego medido junto al rio pesa poco frente a eso."),
    ("uru_uru", "Desvio de rios para riego, sedimentos del Desaguadero, aguas servidas de Oruro y mineria de Huanuni.",
     [("elDiario.es", "https://www.eldiario.es/sociedad/lago-boliviano-declarado-sitio-ramsar-ahora-desertico-basurero_1_7370264.html"),
      ("Los Tiempos", "https://www.lostiempos.com/actualidad/pais/20210323/mar-plastico-alarma-contaminacion-lago-uru-uru")],
     "Parcial", "Aguas arriba: el agua que trae el Desaguadero explica el 93% de la perdida (R2 0.92). La mineria y "
                "las aguas servidas de Oruro estan en el inventario de OpenStreetMap, pero no se puede medir su efecto en "
                "el volumen."),
    ("titicaca_menor", "Lluvia y evaporacion dominan; el riego pesa poco. El minimo de 2023 se debio a la sequia.",
     [("Lima-Quispe et al. 2025", "https://hess.copernicus.org/articles/29/655/2025/hess-29-655-2025.pdf"),
      ("Los Tiempos 2023", "https://www.lostiempos.com/tendencias/medio-ambiente/20231002/nivel-del-lago-titicaca-desciende-su-minimo-historico-sequia")],
     "Parcial", "Ya no culpa a la accion humana (su sospechoso venia de un error: datos MODIS desde 2001 rellenados "
                "con ceros). Queda incalculable: con lluvia medida por satelite el clima explica poco de la caida; falta "
                "el nivel medido del lago."),
    ("pozuelos", "Ciclos naturales de sequia; en los anos secos de los 90 casi desaparece.",
     [("Ficha de la reserva", "https://www.argentina.travel/actividades/monumento-natural-laguna-de-los-pozuelos")],
     "Coincide", "Intacta y casi seca en 1994-1996."),
]
VERDICT_COLOR = {"Coincide": OK, "Parcial": PART, "En tension": BAD}

# Calibracion: lagunas con causa publicada. Esperado: "humana", "natural" (clima, sin tendencia humana) o "mixta".
CALIBRATION = [
    ("concepcion", "humana", "Desmonte y agricultura; desvio de un rio a un arrozal",
     "https://es.mongabay.com/2025/10/bolivia-sitios-ramsar-amenazados/"),
    ("pozuelos", "natural", "Ciclos naturales de sequia en un area protegida",
     "https://www.argentina.travel/actividades/monumento-natural-laguna-de-los-pozuelos"),
    ("colorada", "natural", "Area protegida (Ramsar); baja en las sequias",
     "https://eju.tv/?p=714654"),
    ("verde", "natural", "Area protegida; baja en las sequias", "https://eju.tv/?p=714654"),
    ("poopo", "mixta", "Clima mas riego y desvio del Desaguadero", "https://www.mdpi.com/2072-4292/9/3/218"),
    ("uru_uru", "mixta", "Desvios, sedimentos, aguas servidas de Oruro y mineria",
     "https://www.eldiario.es/sociedad/lago-boliviano-declarado-sitio-ramsar-ahora-desertico-basurero_1_7370264.html"),
    ("titicaca_menor", "natural", "Lluvia y evaporacion dominan; minimo de 2023 por sequia",
     "https://hess.copernicus.org/articles/29/655/2025/hess-29-655-2025.pdf"),
    ("alalay", "mixta", "Aguas servidas, cultivos que tapan la entrada, sedimentos y sequia",
     "https://www.lostiempos.com/actualidad/local/20161012/alalay-se-seca-llegan-menos-aves"),
    ("caceres", "mixta", "Sedimentacion por deforestacion y sequia",
     "https://noticiasfides.com/docs/news/2023/12/conclusiones-segundo-seminario-internacional__1701811989.pdf"),
]


def score(expected: str, state: str) -> str:
    """Acierto, parcial, sin respuesta o error, segun la causa publicada."""
    if state == "Incalculable":
        return "Sin respuesta"
    if expected == "humana":
        return "Acierto" if state == "Huella humana" else "Parcial" if state == "Aguas arriba" else "Error"
    if expected == "natural":
        return "Acierto" if state in ("Intacto", "Causa climatica") else "Error"
    return "Parcial" if state in ("Huella humana", "Aguas arriba", "Causa climatica") else "Error"
# robustez: cuantas de las 6 memorias del lago dan el mismo veredicto (uma/engine.py run_ensemble)


def render(results: list[dict]) -> None:
    by_id = {r["body_id"]: r for r in results}
    ui.md(ui.heading("shield-check", "Como lo verificamos"))
    ui.md("<div class='muted'>Cada numero del detector se contrasta con fuentes que el motor no usa, y cada veredicto "
          "con estudios y prensa. Lo que no coincide se muestra igual.</div>")
    v = data.json_file(data.DATA / "verificacion.json") or {}
    lag = v.get("lagunas", {})
    r_water = [x["r_agua_landsat_mapbiomas"] for x in lag.values() if _num(x.get("r_agua_landsat_mapbiomas"))]
    r_rain = [x["r_lluvia_power_chirps"] for x in lag.values() if _num(x.get("r_lluvia_power_chirps"))]
    cal = [(by_id[b], exp, fact, url, score(exp, by_id[b]["state"])) for b, exp, fact, url in CALIBRATION if b in by_id]
    tally = {k: sum(1 for c in cal if c[4] == k) for k in ("Acierto", "Parcial", "Sin respuesta", "Error")}
    cols = st.columns(4)
    kp = [("satellite", f"{min(r_water):.2f}-{max(r_water):.2f}" if r_water else "-", "Agua Landsat vs MapBiomas (r)", OK),
          ("cloud-sun-rain", f"{min(r_rain):.2f}-{max(r_rain):.2f}" if r_rain else "-", "Lluvia NASA POWER vs CHIRPS (r)",
           PART),
          ("circle-check", f"{tally['Error']} errores", f"En {len(cal)} lagunas con causa publicada "
           f"({tally['Acierto']} aciertos, {tally['Parcial']} parciales)", th.ACCENT),
          ("circle-help", str(sum(1 for r in results if r["state"] == "Incalculable")), "Incalculables, con su motivo",
           th.state_color("Incalculable"))]
    for col, (icon, val, txt, c) in zip(cols, kp):
        with col:
            ui.md(ui.kpi(icon, val, txt, c))

    st.write("")
    ui.md(ui.heading("gauge", "Calibracion: que tanto acierta", 3))
    colors = {"Acierto": OK, "Parcial": PART, "Sin respuesta": "#8b93b8", "Error": BAD}
    rows = "".join(
        f"<tr><td><b>{r['name'].split(' (')[0]}</b></td><td>{exp}</td><td>{ui.pill(r['state'])}</td>"
        f"<td style='color:{colors[sc]};font-weight:800'>{sc}</td>"
        f"<td class='muted'>{fact} (<a href='{url}' target='_blank'>fuente</a>)"
        + (" · datos de agua de calidad baja" if (r.get("data_quality") or {}).get("level") == "baja" else "")
        + "</td></tr>" for r, exp, fact, url, sc in cal)
    ui.md("<div style='overflow-x:auto'><table style='width:100%;border-collapse:collapse'>"
          "<tr class='muted'><th align='left'>Laguna</th><th align='left'>Causa publicada</th><th align='left'>"
          "Detector</th><th align='left'>Resultado</th><th align='left'>Detalle</th></tr>" + rows + "</table></div>")
    st.caption("Acierto: coincide con la causa publicada. Parcial: reconoce una causa no climatica pero no la nombra "
               "entera. Sin respuesta: el detector dice incalculable en vez de adivinar. Error: culpa a la accion humana "
               "cuando es natural, o al reves. Tres de los aciertos o parciales se apoyan en series de agua de calidad "
               "baja: lagunas chicas o con agua de color (la Colorada es roja).")
    st.write("")
    ui.md(ui.heading("scroll-text", "Veredictos frente a estudios y prensa", 3))
    for bid, fact, links, verdict, note in PUBLISHED:
        r = by_id.get(bid)
        if not r:
            continue
        c = VERDICT_COLOR[verdict]
        src = " · ".join(f"<a href='{u}' target='_blank'>{t}</a>" for t, u in links)
        with st.container(border=True):
            ui.md(f"<div style='display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap'>"
                  f"<div style='font-weight:800'>{r['name']}</div>"
                  f"<span class='chip' style='color:{c};border-color:{c}'>{verdict}</span></div>"
                  f"<div style='margin:6px 0'>{ui.pill(r['state'])} <span class='muted'>confianza "
                  f"{r['confidence'].lower()}</span></div>"
                  f"<div><b>Lo publicado:</b> {fact} <span class='muted'>({src})</span></div>"
                  f"<div><b>El detector:</b> {note}</div>")

    st.write("")
    left, right = st.columns(2, gap="large")
    with left, st.container(border=True):
        ui.md(ui.heading("satellite", "El agua medida por dos fuentes", 3))
        pick = st.selectbox("Laguna", [k for k, x in lag.items() if x.get("agua_mapbiomas")],
                            format_func=lambda k: by_id[k]["name"] if k in by_id else k, key="ver_pick")
        if pick:
            x = lag[pick]
            df = pd.DataFrame([{"ano": int(y), "ha": h, "fuente": name}
                               for name, key in (("Landsat (este detector)", "agua_landsat"),
                                                 ("MapBiomas Agua (independiente)", "agua_mapbiomas"))
                               for y, h in x[key].items()])
            ch = alt.Chart(df).mark_line(point=True, strokeWidth=2.5).encode(
                x=alt.X("ano:O", title=None, axis=alt.Axis(values=list(range(1985, 2025, 5)))),
                y=alt.Y("ha:Q", title="Hectareas de agua"),
                color=alt.Color("fuente:N", scale=alt.Scale(range=[th.ACCENT, th.ACCENT_2]),
                                legend=alt.Legend(orient="bottom", title=None)))
            st.altair_chart(ch, width="stretch")
            st.caption(f"Correlacion r = {x['r_agua_landsat_mapbiomas']:.2f}. Lluvia: NASA POWER "
                       f"{x['lluvia_media_power_mm']} mm/ano y CHIRPS {x['lluvia_media_chirps_mm']} mm/ano "
                       f"(r = {x['r_lluvia_power_chirps']:.2f}); el motor usa el promedio de las dos.")
    with right, st.container(border=True):
        ui.md(ui.heading("gauge", "Limites conocidos", 3))
        items = [
            "No predice el nivel del agua: es una herramienta de atribucion. En la prueba hacia atras el error medio "
            f"va de {min(r['backtest']['mae_pct'] for r in results if r.get('backtest')):.0f}% a "
            f"{max(r['backtest']['mae_pct'] for r in results if r.get('backtest')):.0f}%.",
            "Prueba coincidencia y consistencia en el tiempo, no causalidad estricta.",
            "Si el modelo de clima no es significativo (p >= 0.05) o la gemela de control no es estable, la prueba "
            "no se evalua y el caso puede quedar incalculable, con el motivo escrito.",
            "Poblacion, luces nocturnas y ciudad en la cuenca son sospechosos indirectos: acompanan, pero no culpan.",
            "Un sospechoso medido en hectareas tiene que crecer al menos el 10% del agua perdida para contar.",
            "Las lluvias de NASA POWER y CHIRPS discrepan en el Chaco y la Chiquitania (r ~0.55).",
            "El caudal del Desaguadero se estima por el agua visible en el cauce: no hay estaciones de caudal en el "
            "analisis. Las obras de regulacion a la salida del Titicaca y lo que se lleva el Mauri en Peru no se ven "
            "desde el satelite.",
            "El verde en epoca seca junto al rio incluye bofedales naturales; Landsat 8/9 se ajusta a la escala de "
            "5/7 (Roy et al. 2016) para que el cambio de satelite no parezca riego nuevo.",
        ]
        ui.md("<div class='why' style='margin-top:0'><ul>" + "".join(f"<li>{t}</li>" for t in items) + "</ul></div>")
        bol = v.get("bolivia")
        if bol:
            ui.md(ui.kpi("droplets", f"{bol['2024_vs_media_pct']:+.0f}%",
                         "Agua de Bolivia en 2024 frente a su media 1985-2024 (MapBiomas Agua)", th.NATURAL))

    db = data.DATA / "uma.db"
    if db.exists():
        with st.expander("Corridas del motor registradas (auditoria)"), sqlite3.connect(db) as con:
            runs = pd.read_sql("SELECT run_id AS corrida, created_at AS fecha, note AS cambio, "
                               "substr(code_sha256,1,10) AS codigo, substr(inputs_sha256,1,10) AS datos "
                               "FROM runs ORDER BY run_id DESC", con)
            st.dataframe(runs, hide_index=True, width="stretch")
            st.caption("Cada corrida guarda la huella (hash) del codigo y de los datos: cualquiera puede repetirla y "
                       "comprobar que da lo mismo.")


def _num(x) -> bool:
    return isinstance(x, (int, float)) and x == x
