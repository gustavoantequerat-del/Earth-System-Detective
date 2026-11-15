"""Pregunta al detector: chat en lenguaje sencillo, anclado a los resultados (Claude) o con respuestas guiadas."""
from __future__ import annotations

import streamlit as st

import ai
import ui

SUGGESTED = ["Que esta pasando con el agua en Bolivia?", "Por que se esta secando el lago Poopo?",
             "Que lagunas tienen huella humana y por que?", "Que tan seguros son estos resultados?",
             "Que puede hacer mi comunidad?"]


def render(results: list[dict], national: list[dict], by_id: dict) -> None:
    ui.md(ui.heading("search", "Pregunta al detector"))
    ui.md("<div class='muted'>Escribe tu pregunta como se la harias a una persona. Las respuestas salen solo de los "
          "datos del detector y dicen que tan seguras son.</div>")
    c1, c2 = st.columns([3, 1])
    with c2:
        lang = st.selectbox("Idioma", list(ai.LANGS), key="ai_lang")
    with c1:
        focus = st.selectbox("Sobre", ["Todo el pais"] + [r["body_id"] for r in results], key="ai_focus",
                             format_func=lambda i: i if i == "Todo el pais" else by_id[i]["name"])
    ctx = ai.overview_context(results, national)
    if focus != "Todo el pais":
        ctx = {"laguna_elegida": ai.body_context(by_id[focus]), "resumen_pais": ctx}

    if not ai.available():
        st.info("El asistente con IA se activa con una clave de Anthropic (ANTHROPIC_API_KEY en los secretos de "
                "Streamlit o en .env). Mientras tanto, aqui va la explicacion sencilla armada con los datos.")
        for r in ([by_id[focus]] if focus != "Todo el pais" else results):
            with st.container(border=True):
                txt = ai.plain_summary(r)
                ui.md(f"<div style='margin-bottom:6px'>{ui.pill(r['state'])}</div>")
                st.markdown(txt)
                ai.speak_button(txt)
        return

    hist = st.session_state.setdefault("ai_chat", [])
    def _ask():
        st.session_state.ai_pending = st.session_state.ai_sugg
        st.session_state.ai_sugg = None

    st.pills("Preguntas frecuentes", SUGGESTED, key="ai_sugg", label_visibility="collapsed", on_change=_ask)
    for m in hist:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
    q = st.chat_input("Escribe tu pregunta") or st.session_state.pop("ai_pending", None)
    if q:
        with st.chat_message("user"):
            st.markdown(q)
        with st.chat_message("assistant"):
            answer = st.write_stream(ai.stream(q, ctx, lang, hist[-8:]))
        hist += [{"role": "user", "content": q}, {"role": "assistant", "content": answer}]
        ai.speak_button(answer, lang)
    if hist and st.button("Nueva conversacion"):
        st.session_state.ai_chat = []
        st.rerun()
    st.caption("Respuestas generadas por IA (Claude) a partir de los resultados del detector. Pueden equivocarse: "
               "verifica en la ficha de cada laguna.")
