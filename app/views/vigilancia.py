"""Vigilancia semanal de incendios (NASA FIRMS) en las cuencas de los cuerpos de agua en riesgo."""
from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

import data
import theme as th
import ui

FIRE = "#ff8a65"


def _secret(name: str) -> str | None:
    import os
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:  # sin archivo de secretos
        pass
    return os.environ.get(name)


def _telegram(wk: dict) -> None:
    """Envia el resumen de la semana al canal de Telegram configurado (token en secretos o en .env)."""
    import os
    import sys
    sys.path.insert(0, str(data.ROOT))
    from uma import alerts
    alerts.load_env()
    tok, chat = _secret("TELEGRAM_BOT_TOKEN"), _secret("TELEGRAM_CHAT_ID")
    with st.container(border=True):
        c1, c2 = st.columns([3, 1], gap="medium")
        with c1:
            ui.md(ui.heading("bell-ring", "Alertas en vivo por Telegram", 3) +
                  ("<div class='muted'>Canal configurado. El boton envia el resumen de esta semana.</div>" if tok and chat
                   else "<div class='muted'>Sin configurar. Crea un bot con @BotFather, agregalo a un canal y guarda "
                        "TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID en .env (local) o en los secretos de Streamlit.</div>"))
        with c2:
            if st.button("Enviar alerta de prueba", disabled=not (tok and chat), width="stretch", type="primary"):
                os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"] = tok, chat
                import datetime as dt
                text = "[PRUEBA] " + alerts.message(wk["rows"], dt.date.fromisoformat(wk["week_end"]))
                try:
                    st.success(f"Enviado ({alerts.send_telegram(text)}).")
                except OSError as e:
                    st.error(f"No se pudo enviar: {e}")


def render() -> None:
    ui.md(ui.heading("flame", "Vigilancia semanal de incendios", 2, FIRE))
    wk = data.weekly()
    if not wk:
        st.info("Todavia no se corrio la vigilancia: python -m uma.alerts --project TU-PROYECTO --dry-run")
        return
    hot = [x for x in wk["rows"] if x["alerta"]]
    current = {r["body_id"]: r["state"] for r in data.results()}  # estado vigente, no el de la semana revisada
    c1, c2, c3 = st.columns(3)
    with c1:
        ui.md(ui.kpi("bell-ring", str(len(hot)), "Alertas esta semana", FIRE if hot else th.state_color("Intacto")))
    with c2:
        ui.md(ui.kpi("droplets", str(len(wk["rows"])), "Cuerpos de agua vigilados", th.ACCENT, 0.07))
    with c3:
        ui.md(ui.kpi("info", wk["week_end"], f"Semana revisada · avisos: {wk['notified'][:28]}", th.ACCENT_2, 0.14))
    st.write("")
    for start in range(0, len(wk["rows"]), 2):
        cols = st.columns(2, gap="large")
        for col, x in zip(cols, wk["rows"][start:start + 2]):
            with col, st.container(border=True):
                head = ui.pulse_dot(FIRE) if x["alerta"] else ""
                ui.md(f"<div style='font-weight:800;font-size:1.05rem'>{head}{x['name']}</div>"
                      f"<div style='margin:6px 0'>{ui.pill(current.get(x['body_id'], x['state']))}</div>")
                m = max([max(a["focos"], a["normal"]) for a in x["areas"].values()] + [1])
                items = []
                for nm, a in x["areas"].items():
                    where = "cerca" if nm == "cerca" else "cuenca"
                    items += [(f"Focos esta semana ({where})", a["focos"], FIRE if a["alerta"] else "#ffb59e"),
                              (f"Normal para esta semana ({where})", a["normal"], "#4a5378")]
                ui.md(ui.bars(items, "", m))
    _telegram(wk)
    st.caption("Alerta si un cuerpo de agua en riesgo tiene al menos 5 focos y el doble de lo normal (promedio de la "
               "misma semana en los 5 anos anteriores). Prueba retroactiva: la semana al 2019-08-25 dispara la alerta "
               "en la laguna de la Chiquitania este (163 focos cerca contra 1.2 normales).")
    db = data.DATA / "uma.db"
    if db.exists():
        with st.expander("Historial de la vigilancia"), sqlite3.connect(db) as con:
            try:
                h = pd.read_sql("SELECT week_end AS semana, body_id, area, fires AS focos, normal, alert AS alerta, "
                                "notified AS aviso FROM operational_alerts ORDER BY week_end DESC", con)
                st.dataframe(h, hide_index=True, width="stretch")
            except Exception:  # tabla aun no creada
                st.caption("Sin historial.")
