"""Panorama: tablero con indicadores, vistas agregadas y una tarjeta por cuerpo de agua."""
from __future__ import annotations

import pandas as pd
import streamlit as st

import data
import nav
import theme as th
import ui


def render(results: list[dict], visible: list[dict], national: list[dict]) -> None:
    ui.md(ui.hero("Detector de huella humana",
                  "Por que se pierde el agua en Bolivia: clima natural o accion humana, con evidencia auditable."))
    main = [r for r in visible if r["body_id"] not in data.controls(results) or r["state"] == "Huella humana"]
    _kpis(main, national)
    st.write("")
    left, right = st.columns([1, 1], gap="large")
    with left, st.container(border=True):
        ui.md(ui.heading("chart-pie", "Veredictos", 3))
        _state_donuts(main, national)
    with right, st.container(border=True):
        ui.md(ui.heading("chart-column", "De donde viene el agua perdida", 3))
        _loss_by_cause(main)
    st.write("")
    ui.md(ui.heading("droplets", "Cuerpos de agua con analisis completo"))
    _cards(sorted(main, key=lambda r: (th.SEVERITY[r["state"]], r["trend"]["change_pct"])))
    st.write("")
    left, right = st.columns([1, 1], gap="large")
    with left, st.container(border=True):
        ui.md(ui.heading("mountain", "Por region", 3))
        _by_region(main, national)
    with right, st.container(border=True):
        ui.md(ui.heading("factory", "Agua artificial en Bolivia", 3, th.ARTIFICIAL))
        _artificial()


def _kpis(main: list[dict], national: list[dict]) -> None:
    lost = sum(max(0.0, r["baseline_mean_ha"] * -r["trend"]["change_pct"] / 100) for r in main)
    wk = data.weekly()
    fires = sum(1 for x in (wk or {}).get("rows", []) if x["alerta"])
    count = lambda s: sum(1 for r in main if r["state"] == s)  # noqa: E731
    items = [
        ("droplets", f"{len(main)}", "Analisis completos", th.ACCENT),
        ("footprints", f"{count('Huella humana')}", "Con huella humana", th.state_color("Huella humana")),
        ("circle-help", f"{count('Incalculable')}", "Incalculables (con motivo)", th.state_color("Incalculable")),
        ("trending-down", f"{lost / 1000:,.0f} mil ha", "Agua perdida (ultimos 5 anos)", th.ACCENT_2),
        ("flame", f"{fires}", "Alertas de incendio esta semana", "#ff8a65"),
        ("scan", f"{len(national)}", "Lagunas en el barrido nacional", th.NATURAL if national else th.MUTED),
    ]
    cols = st.columns(3)
    for i, (icon, value, label, color) in enumerate(items):
        with cols[i % 3]:
            ui.md(ui.kpi(icon, value, label, color, delay=i * 0.07))


def _state_donuts(main: list[dict], national: list[dict]) -> None:
    colors = {s: v["color"] for s, v in th.STATES.items()}
    sets = [("Analisis completo", main)] + ([("Barrido nacional", national)] if national else [])
    cols = st.columns(len(sets))
    for col, (title, rows) in zip(cols, sets):
        counts = {s: sum(1 for r in rows if r["state"] == s) for s in th.STATES}
        with col:
            ui.md(f"<div style='text-align:center'>{ui.donut(counts, colors, str(len(rows)))}"
                  f"<div class='muted'>{title}</div></div>")
    ui.md("<div class='legend'>" + "".join(
        f"<span class='chip' style='color:{v['color']}'>{ui.ic.svg(v['icon'], v['color'], 14, 2.4)}{s}</span>"
        for s, v in th.STATES.items()) + "</div>")


def _loss_by_cause(main: list[dict]) -> None:
    totals: dict[str, float] = {}
    for r in main:
        for k, v in r["decomposition_ha"].items():
            totals[k] = totals.get(k, 0.0) + min(v, 0.0)  # solo perdidas
    color = {"Lluvia menos evaporacion": "#ffa26b", "El Nino": "#ffd166", "Huella humana": "#ff7a7a",
             "Menos agua desde aguas arriba": "#60a5fa",
             "Incalculable": "#8b93b8"}
    items = [(k, -v, color.get(k, th.MUTED)) for k, v in sorted(totals.items(), key=lambda kv: kv[1]) if v < 0]
    ui.md(ui.bars(items, " ha"))
    splits = [r["upstream_split"] for r in main if r.get("upstream_split")]
    if splits:
        hi = sum(x["human_max_ha"] for x in splits)
        lo = sum(x["human_min_ha"] for x in splits)
        ui.md(f"<div class='why' style='margin-top:6px'>De lo que deja de llegar aguas arriba, la parte humana va de "
              f"<b>{lo:,} a {hi:,} ha</b>. Es un rango porque la fuente (el Titicaca) tiene un veredicto de confianza "
              "baja; se cierra con el nivel medido del lago y el caudal del Desaguadero en estaciones.</div>")
    ui.md("<div class='muted'>Suma de las perdidas de todos los cuerpos de agua con analisis completo. "
          "\"Incalculable\" es agua perdida cuya causa no se puede calcular con los datos actuales.</div>")


def _cards(rows: list[dict]) -> None:
    for start in range(0, len(rows), 3):
        cols = st.columns(3, gap="medium")
        for col, r in zip(cols, rows[start:start + 3]):
            with col, st.container(border=True):
                color = th.state_color(r["state"])
                top = next((s for s in r["suspects"] if not s.get("indirect")), None)
                ui.md(f"<div style='font-weight:800;font-size:1.05rem'>{r['name'].split(' (')[0]}</div>"
                      f"<div style='margin:6px 0'>{ui.pill(r['state'])}</div>")
                c1, c2 = st.columns([3, 2])
                with c1:
                    ui.md(f"<div style='font-size:1.8rem;font-weight:900;color:{color}'>"
                          f"{r['trend']['change_pct']:+.0f}%</div><div class='muted'>agua vs 1985-2000</div>")
                with c2:
                    ui.md(ui.ring(r["n_pass"] / 3, color, f"{r['n_pass']}/3", 70))
                ui.md(ui.sparkline(r["observed"], color))
                rb = r.get("robustness")
                if rb:
                    ui.md(f"<div class='muted'>Se mantiene en {rb['agree']} de {rb['of']} configuraciones"
                          + (" · robusto" if rb["agree"] >= 5 else " · fragil" if rb["agree"] <= 3 else "") + "</div>")
                if r.get("upstream_source"):
                    ui.md(ui.chip(f"Fuente: {r['upstream_source']['name'].split(' (')[0]}", "waves", "#60a5fa"))
                elif top:
                    ui.md(ui.chip(f"{top['label']} · {top['evidence']}", "search"))
                nav.open_button(r["body_id"], f"card_{r['body_id']}")


def _by_region(main: list[dict], national: list[dict]) -> None:
    rows = [{"region": data.region(r["lat"], r["lon"]), "estado": r["state"]} for r in main + national]
    if not rows:
        return
    df = pd.DataFrame(rows).value_counts().rename("n").reset_index()
    for reg, g in df.groupby("region"):
        total = int(g.n.sum())
        segs = "".join(f"<span title='{e}: {n}' style='display:block;height:100%;width:{100 * n / total:.1f}%;"
                       f"background:{th.state_color(e)};animation:grow 1s ease'></span>"
                       for e, n in sorted(zip(g.estado, g.n), key=lambda x: th.SEVERITY[x[0]]))
        ui.md(f"<div style='margin:10px 0 4px 0;display:flex;justify-content:space-between'><b>{reg}</b>"
              f"<span class='muted'>{total} cuerpos de agua</span></div>"
              f"<div class='bar' style='height:16px;display:flex'>{segs}</div>")
    ui.md("<div class='muted' style='margin-top:8px'>Incluye el barrido nacional (diagnostico rapido).</div>")


def _artificial() -> None:
    art = data.artificial_points()
    if not art:
        st.caption("Sin capa de agua artificial: python -m uma.artificial_map --project TU-PROYECTO")
        return
    df = pd.DataFrame(art["points"])
    by = df.groupby("tipo").agg(n=("ha", "size"), ha=("ha", "sum")).sort_values("ha", ascending=False)
    palette = [th.ARTIFICIAL, "#7dd3fc", "#a5b4fc"]
    ui.md(ui.bars([(f"{t} ({int(r.n):,})", r.ha, palette[i % 3]) for i, (t, r) in enumerate(by.iterrows())], " ha"))
    ui.md(f"<div class='muted'>{len(df):,} manchas de agua artificial en {art['year']} (MapBiomas Agua). "
          "Represas, estanques y pozas mineras: la mitad de las tendencias opuestas.</div>")
