"""Ficha de un cuerpo de agua: veredicto, motivos, antes/despues, causas, pruebas, alrededores y auditoria."""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

import data
import icons as ic
import map3d
import theme as th
import ui

TABS = ["Antes y despues", "Clima y causas", "Agua natural vs artificial", "Pruebas y sospechosos", "Alrededores",
        "Auditoria"]
TAB_ICONS = ["satellite", "chart-line", "droplets", "search", "map-pin", "scroll-text"]
TEST_NAMES = {"clima": "1. Lo que el clima no explica", "control": "2. Gemela de control",
              "coincidencia": "3. Coincidencia en el tiempo"}
SUSPECT_PLACE = {"mining_ha": ["Mina o cantera"], "mining_water_ha": ["Mina o cantera"],
                 "urban_ha": ["Ciudad o pueblo", "Industria"], "population": ["Ciudad o pueblo"],
                 "night_lights": ["Industria", "Ciudad o pueblo"], "artificial_water_ha": ["Represa o canal"],
                 "dry_crop_ha": ["Represa o canal"], "crop_water_hm3": ["Represa o canal"]}
SUSPECT_CHANGE = {"mining_ha": "mining", "mining_water_ha": "mining", "urban_ha": "urban", "population": "urban",
                  "night_lights": "urban", "agri_ha": "agri", "dry_crop_ha": "agri", "crop_water_hm3": "agri",
                  "pasture_ha": "pasture", "forest_loss_ha": "forest_loss", "burned_ha": "forest_loss"}


def render(options: list[str], by_id: dict) -> None:
    def _pick():
        st.session_state.sel = st.session_state.pick

    if st.session_state.sel not in options:
        st.session_state.sel = options[0]
    st.session_state.pick = st.session_state.sel
    sel = st.selectbox("Cuerpo de agua", options, key="pick", on_change=_pick,
                       format_func=lambda i: f"{by_id[i]['name']} · {by_id[i]['state']}")
    r = by_id[sel]
    _header(r)
    _explain(r)
    _pdf_button(r)
    from views import rio
    has_rio = rio.available(sel)
    names, icons_ = TABS + (["El rio"] if has_rio else []), TAB_ICONS + (["waves"] if has_rio else [])
    ui.md(ic.css_rules([(f'[data-testid="stTabs"] [role="tab"]:nth-of-type({i + 1}) [data-testid="stMarkdownContainer"] p',
                         n, th.ACCENT_2, 16) for i, n in enumerate(icons_)]))
    tabs = st.tabs(names)
    if has_rio:
        with tabs[6]:
            rio.render(sel)
    with tabs[0]:
        _before_after(sel, r)
    with tabs[1]:
        _climate(r)
    with tabs[2]:
        _opposite_trends(sel, r)
    with tabs[3]:
        _tests(r)
    with tabs[4]:
        _surroundings(sel, r)
    with tabs[5]:
        _audit(sel, r)


def _header(r: dict) -> None:
    color = th.state_color(r["state"])
    top = next((s for s in r["suspects"] if not s.get("indirect")), None)
    with st.container(border=True):
        c1, c2, c3 = st.columns([3, 1, 3], gap="large")
        with c1:
            ui.md(f"<div style='font-weight:900;font-size:1.6rem'>{r['name']}</div>"
                  f"<div style='margin:10px 0'>{ui.pill(r['state'], big=True)}</div>"
                  f"<div class='muted'>{th.ACTION[r['state']]}</div>")
        with c2:
            label = f"{r['n_pass']}/3"
            ui.md(f"<div style='text-align:center'>{ui.ring(r['n_pass'] / 3, color, label, 96)}"
                  f"<div class='muted'>pruebas · confianza {r['confidence'].lower()}</div></div>")
        with c3:
            ui.md(f"<div style='display:flex;justify-content:space-between'><span class='muted'>Agua 1985-2024</span>"
                  f"<b style='color:{color};font-size:1.4rem'>{r['trend']['change_pct']:+.0f}%</b></div>"
                  + ui.sparkline(r["observed"], color, height=70))
            chips = [ui.chip(f"Tendencia {r['trend']['sen_ha_per_year']:+,.0f} ha/ano", "trending-down")]
            if r.get("upstream_source"):
                chips.append(ui.chip(f"Fuente: {r['upstream_source']['name'].split(' (')[0]}", "waves", "#60a5fa"))
            elif top:
                chips.append(ui.chip(top["label"], "search"))
            q = r.get("data_quality") or {}
            if q.get("r_jrc") is not None:
                chips.append(ui.chip(f"Calidad {q['level']} (r={q['r_jrc']:.2f})", "gauge"))
            if data.share_pct(r) is not None:
                chips.append(ui.chip(("Fuente y clima explican" if r.get("upstream_source") else "Clima explica")
                                     + f" {data.share_pct(r)}%", "cloud-sun-rain"))
            rb = r.get("robustness")
            if rb:
                chips.append(ui.chip(f"Robustez {rb['agree']}/{rb['of']} memorias", "gauge",
                                     "#5ee6a8" if rb["agree"] >= 5 else "#ffd166"))
            prot = data.protection(r["body_id"])
            if prot["ramsar"]:
                chips.append(ui.chip(f"Sitio Ramsar: {prot['ramsar']}", "shield-check", "#5ee6a8"))
            elif prot["areas"]:
                chips.append(ui.chip(f"Area protegida: {prot['areas'][0].split(' (')[0]}", "shield-check", "#5ee6a8"))
            ui.md("".join(chips))
        if r.get("why"):
            title = "Por que es incalculable" if r["state"] == "Incalculable" else "Lo que hay que saber"
            ui.md(f"<div class='why'><div class='h' style='margin:0'>{ic.svg('triangle-alert', '#ffd166', 18, 2.4)}"
                  f"{title}</div><ul>" + "".join(f"<li>{w}</li>" for w in r["why"]) + "</ul></div>")


def _explain(r: dict) -> None:
    """Explicacion en lenguaje sencillo (Claude si hay clave; si no, plantilla con los mismos datos)."""
    import ai
    with st.expander("Explicamelo facil", icon=":material/record_voice_over:"):
        lang = st.segmented_control("Idioma", list(ai.LANGS), default="Espanol", key=f"lang_{r['body_id']}",
                                    label_visibility="collapsed") or "Espanol"
        key = f"exp_{r['body_id']}_{lang}"
        if ai.available():
            if key not in st.session_state and st.button("Explicar con IA", type="primary", key=f"b_{key}"):
                st.session_state[key] = st.write_stream(ai.stream(
                    "Explica a una persona sin estudios tecnicos que le esta pasando a esta laguna, por que, que tan "
                    "seguro esta el detector y que se puede hacer.", ai.body_context(r), lang))
            elif key in st.session_state:
                st.markdown(st.session_state[key])
            if key in st.session_state:
                ai.speak_button(st.session_state[key], lang)
                st.caption("Generado por IA (Claude) a partir de los datos de esta ficha. Puede equivocarse.")
        else:
            txt = ai.plain_summary(r)
            st.markdown(txt)
            ai.speak_button(txt)
            st.caption("Explicacion armada con los datos. Con una clave de Anthropic se activa la explicacion con IA "
                       "en espanol, quechua, aymara o ingles.")


@st.cache_data(show_spinner=False)
def _pdf(body_id: str, results_mtime: float) -> bytes:
    import report
    r = next(x for x in data.results() if x["body_id"] == body_id)
    return report.build(r, data.protection(body_id), data.CTX, data.IMG, data.context_meta(body_id),
                        data.fires_for(body_id), th.ACTION[r["state"]])


def _pdf_button(r: dict) -> None:
    c1, c2 = st.columns([1, 3])
    with c1:
        if st.button("Preparar ficha PDF", width="stretch", key=f"pdfprep_{r['body_id']}"):
            st.session_state[f"pdf_{r['body_id']}"] = True
    with c2:
        if st.session_state.get(f"pdf_{r['body_id']}"):
            with st.spinner("Armando el PDF..."):
                pdf = _pdf(r["body_id"], data._mtime(data.DATA / "results.json"))
            st.download_button("Descargar ficha PDF", pdf, file_name=f"ficha_{r['body_id']}.pdf",
                               mime="application/pdf", type="primary", key=f"pdfdl_{r['body_id']}")
        else:
            ui.md("<div class='muted' style='padding-top:8px'>Una pagina para llevar a la reunion: veredicto, pruebas, "
                  "sospechosos, proteccion legal, antes y despues, y fuentes.</div>")


def _before_after(sel: str, r: dict) -> None:
    meta = data.context_meta(sel)
    views = ["La laguna"] + (["Los alrededores: que aparecio"] if meta else [])
    vw = st.segmented_control("Vista", views, default=views[-1], key="ba_view", label_visibility="collapsed") or views[-1]
    if vw.startswith("Los alrededores"):
        ya, yb = meta["years"]
        legend = {k: dict(v, ha=meta["changes_ha"].get(k, 0)) for k, v in meta["legend"].items()}
        st.iframe(map3d.before_after_html(data.CTX / f"{sel}_antes.png", data.CTX / f"{sel}_despues.png", str(ya),
                                                str(yb), changes=data.CTX / f"{sel}_cambios.png", legend=legend,
                                                height=620), height=700)
        st.caption(f"Ventana de {meta['window_km']:.0f} km. Colores: lo que no existia en {ya} y si en {yb} "
                   "(MapBiomas Bolivia; bosque perdido de Hansen).")
        return
    yrs = sorted({int(p.stem.split("_")[-1]) for p in data.IMG.glob(f"{sel}_*.png")
                  if p.stem.split("_")[-1].isdigit()}) if data.IMG.exists() else []
    if len(yrs) < 2:
        st.caption("Sin imagenes para este cuerpo de agua.")
        return
    ca, cb = st.columns(2)
    ya = ca.select_slider("Antes", yrs, value=yrs[0], key="ya")
    yb = cb.select_slider("Despues", yrs, value=yrs[-1], key="yb")
    st.iframe(map3d.before_after_html(data.IMG / f"{sel}_{ya}.png", data.IMG / f"{sel}_{yb}.png", str(ya), str(yb),
                                            data.IMG / f"{sel}_{ya}_water.png", data.IMG / f"{sel}_{yb}_water.png",
                                            height=620), height=680)
    obs = dict(zip(r["years"], r["observed"]))
    if ya in obs and yb in obs:
        st.caption(f"Agua detectada: {obs[ya]:,.0f} ha en {ya} → {obs[yb]:,.0f} ha en {yb}. "
                   "Landsat de epoca seca (junio-octubre), mediana sin nubes.")


def _climate(r: dict) -> None:
    g1, g2 = st.columns([3, 2], gap="large")
    with g1, st.container(border=True):
        ui.md(ui.heading("chart-line", "Observado contra lo que explica el clima", 3))
        ts = pd.DataFrame({"year": r["years"], "Observado": r["observed"], "Esperado por el clima": r["expected"],
                           "oni": r["oni"]})
        long = ts.melt(id_vars=["year"], value_vars=["Observado", "Esperado por el clima"], var_name="serie",
                       value_name="ha")
        xs = alt.Scale(domain=[r["years"][0], r["years"][-1] + 1], zero=False)
        bands = alt.Chart(ts[ts.oni >= 0.5]).mark_rect(opacity=0.16, color="#ffd166").encode(
            x=alt.X("year:Q", scale=xs), x2=alt.X2("year2:Q")).transform_calculate(year2="datum.year + 1")
        lines = alt.Chart(long).mark_line(strokeWidth=3, interpolate="monotone").encode(
            x=alt.X("year:Q", axis=alt.Axis(format="d"), title=None, scale=xs),
            y=alt.Y("ha:Q", title="Superficie de agua (ha)"),
            color=alt.Color("serie:N", scale=alt.Scale(range=[th.ACCENT, th.ACCENT_2]),
                            legend=alt.Legend(orient="bottom", title=None)),
            strokeDash=alt.condition(alt.datum.serie == "Esperado por el clima", alt.value([6, 4]), alt.value([0])))
        rule = alt.Chart(pd.DataFrame({"year": [r["baseline_end"]]})).mark_rule(color=th.MUTED).encode(
            x=alt.X("year:Q", scale=xs))
        st.altair_chart(bands + lines + rule, width="stretch")
        cf = r.get("climate_fit") or {}
        note = ("Modelo de clima confiable" if r.get("climate_reliable") else
                "Modelo de clima NO confiable para esta laguna: la linea esperada queda en el promedio base")
        st.caption(f"{note} (R²={cf.get('r2', r['climate_r2']):.2f}, p={cf.get('f_p', float('nan')):.2f}). "
                   f"Franjas amarillas: El Nino. Linea gris: fin del periodo base ({r['baseline_end']}).")
    with g2, st.container(border=True):
        ui.md(ui.heading("chart-column", "De donde viene el cambio", 3))
        color = {"Lluvia menos evaporacion": "#ffa26b", "El Nino": "#ffd166", "Huella humana": "#ff7a7a",
             "Menos agua desde aguas arriba": "#60a5fa",
                 "Incalculable": "#8b93b8"}
        items = [(k, v, color.get(k, th.MUTED)) for k, v in r["decomposition_ha"].items()]
        m = max((abs(v) for _, v, _ in items), default=1)
        ui.md(ui.bars(items, " ha", m))
        st.caption("Promedio del periodo base contra los ultimos 5 anos; las partes suman el cambio total.")


def _opposite_trends(sel: str, r: dict) -> None:
    sus = data.suspects()
    sw = sus[(sus.body_id == sel) & sus.suspect.isin(["natural_water_ha", "artificial_water_ha", "mining_water_ha"])]
    if sw.empty or "area" not in sw:
        st.caption("Sin series de agua artificial para este cuerpo de agua.")
        return
    areas = [a for a in ("subcuenca_local", "cuenca_aporte") if a in set(sw.area)]
    names = {"subcuenca_local": "Cerca de la laguna", "cuenca_aporte": "Toda la cuenca de aporte"}
    ar = st.segmented_control("Area", areas, default=areas[0], format_func=names.get, key="tend_area",
                              label_visibility="collapsed") or areas[0]
    w = sw[sw.area == ar].pivot_table(index="year", columns="suspect", values="value").reset_index()
    nat = pd.DataFrame({"year": r["years"], "ha": r["observed"], "serie": "Esta laguna (Landsat)"})
    if "natural_water_ha" in w:
        nat = pd.concat([nat, pd.DataFrame({"year": w.year, "ha": w.natural_water_ha, "serie": "Agua natural del area"})])
    art = pd.DataFrame({"year": w.year, "ha": w.get("artificial_water_ha", 0) + w.get("mining_water_ha", 0)})
    xs = alt.Scale(domain=[1985, 2025])
    left = alt.Chart(nat).mark_line(strokeWidth=3, interpolate="monotone").encode(
        x=alt.X("year:Q", axis=alt.Axis(format="d"), title=None, scale=xs),
        y=alt.Y("ha:Q", title="Agua natural (ha)", axis=alt.Axis(titleColor="#5b8cff")),
        color=alt.Color("serie:N", scale=alt.Scale(range=[th.NATURAL, "#5b8cff"]),
                        legend=alt.Legend(orient="bottom", title=None)))
    right = alt.Chart(art).mark_area(opacity=0.4, color=th.ARTIFICIAL, interpolate="monotone",
                                     line={"color": th.ARTIFICIAL, "strokeWidth": 3}).encode(
        x=alt.X("year:Q", scale=xs), y=alt.Y("ha:Q", title="Agua artificial (ha)",
                                             axis=alt.Axis(titleColor=th.ARTIFICIAL)))
    with st.container(border=True):
        st.altair_chart(alt.layer(left, right).resolve_scale(y="independent"), width="stretch")
        a0, a1 = art[art.year.between(1985, 1990)].ha.mean(), art[art.year.between(2020, 2024)].ha.mean()
        ui.md(f"<span class='pill' style='background:{th.ARTIFICIAL}'>{ic.svg('droplets', th.INK, 17, 2.6)}"
              f"Agua artificial: {a0:,.0f} → {a1:,.0f} ha</span> <span class='muted'>(1985-1990 contra 2020-2024). "
              "Si la artificial sube mientras la natural baja, la misma presion humana puede explicar ambas.</span>")


def _tests(r: dict) -> None:
    with st.container(border=True):
        for k, t in r["tests"].items():
            if t["pass"] is None:
                mark = ic.svg("circle-help", "#ffd166", 24, 2.4)
            elif t["pass"]:
                mark = ic.svg("circle-check", th.state_color("Intacto"), 24, 2.6)
            else:
                mark = ic.svg("circle-dashed", th.MUTED, 24, 2.2)
            ui.md(f"<div class='test'>{mark}<div><b>{TEST_NAMES[k]}</b> — {t['detail']}</div></div>")
    if not r["suspects"]:
        return
    sus = pd.DataFrame(r["suspects"])
    sus["Tipo"] = sus.get("indirect", False).map({True: "indirecto", False: "directo"})
    tbl = sus.rename(columns={"label": "Sospechoso", "evidence": "Evidencia", "onset": "Empieza a crecer",
                              "precedes": "Antecede la caida", "r2": "R² con el residuo"})[
        ["Sospechoso", "Tipo", "Evidencia", "Empieza a crecer", "Antecede la caida", "R² con el residuo"]]
    ev = {"fuerte": "#ff7a7a", "media": "#ffa26b", "debil": "#4a5378"}
    st.dataframe(tbl.style.apply(lambda c: [f"background-color:{ev.get(v, '')};color:#fff;font-weight:700" for v in c],
                                 subset=["Evidencia"]), hide_index=True, width="stretch")


def _surroundings(sel: str, r: dict) -> None:
    meta, places = data.context_meta(sel), data.places(sel)
    if not (meta or places):
        st.caption("Sin datos de alrededores. Se generan con: python -m uma.context --project TU-PROYECTO")
        return
    top = [x for x in r["suspects"] if x["evidence"] != "debil" and not x.get("indirect")][:2] or r["suspects"][:1]
    for sp in top:
        key = sp["suspect"].split("@")[0]
        lines = [f"**{sp['label']}** (evidencia {sp['evidence']}, crece desde {sp['onset']})"]
        ck = SUSPECT_CHANGE.get(key)
        if meta and ck and meta["changes_ha"].get(ck):
            lines.append(f"{meta['legend'][ck]['label']} en los alrededores: {meta['changes_ha'][ck]:,} ha "
                         f"entre {meta['years'][0]} y {meta['years'][1]}")
        near = sorted([x for x in places if x["kind"] in SUSPECT_PLACE.get(key, []) and x["name"]],
                      key=lambda x: x["dist_km"])[:3]
        if near:
            lines.append("Lo mas cercano: " + "; ".join(f"[{x['name']}]({x['osm']}) ({x['kind'].lower()}, "
                                                       f"{x['dist_km']} km)" for x in near))
        st.markdown(" · ".join(lines))
    if places:
        pdf = pd.DataFrame(places)
        st.dataframe(pdf[["kind", "name", "detail", "dist_km", "osm"]].rename(columns={
            "kind": "Tipo", "name": "Nombre", "detail": "Detalle", "dist_km": "Distancia (km)", "osm": "OpenStreetMap"}),
            hide_index=True, width="stretch",
            column_config={"OpenStreetMap": st.column_config.LinkColumn(display_text="ver")})
    else:
        st.caption("OpenStreetMap no registra minas, industrias, ciudades ni represas con nombre en esta zona.")


def _audit(sel: str, r: dict) -> None:
    from uma import audit
    if not (data.DATA / "uma.db").exists():
        st.caption("Sin registro de auditoria todavia: se crea al correr run_engine.py.")
        return
    hist, revs, alts = audit.history(data.DATA, sel)
    st.caption("Cada corrida del motor queda registrada con la huella de los datos y del codigo.")
    if len(hist) > 1 and hist.iloc[0]["estado"] != hist.iloc[1]["estado"]:
        st.info(f"El veredicto cambio de **{hist.iloc[1]['estado']}** (corrida {hist.iloc[1]['corrida']}) a "
                f"**{hist.iloc[0]['estado']}** (corrida {hist.iloc[0]['corrida']}). Motivo: {hist.iloc[0]['nota']}")
    st.dataframe(hist, hide_index=True, width="stretch")
    if not alts.empty:
        st.markdown("**Alertas**")
        st.dataframe(alts, hide_index=True, width="stretch")
    with st.form(f"review_{sel}", clear_on_submit=True, border=True):
        st.markdown("**Agregar revision humana**")
        c1, c2 = st.columns(2)
        who = c1.text_input("Quien revisa")
        outcome = c2.selectbox("Resultado", ["En revision", "Confirmado en campo", "Falso positivo", "Requiere mas datos"])
        comment = st.text_area("Comentario")
        if st.form_submit_button("Guardar revision") and who:
            audit.add_review(data.DATA, sel, who, outcome, comment)
            st.success("Revision guardada en la auditoria.")
            st.rerun()
    if not revs.empty:
        st.markdown("**Revisiones**")
        st.dataframe(revs, hide_index=True, width="stretch")
    with st.expander("Modo tecnico"):
        st.write("Ajuste del modelo de clima:", r.get("climate_fit"))
        st.write("Validacion con el pasado:", r["backtest"])
        st.json(r["tests"])
