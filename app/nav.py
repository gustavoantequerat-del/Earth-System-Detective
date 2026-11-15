"""Navegacion entre vistas: la vista activa y el cuerpo de agua elegido viven en session_state."""
from __future__ import annotations

import streamlit as st

VIEWS = ["Panorama", "Mapa", "Cerca de mi", "Pregunta", "Monitoreo", "Ficha", "Vigilancia", "Verificacion"]
ICONS = ["layout-dashboard", "map", "crosshair", "search", "list", "scan-search", "flame", "shield-check"]
ALIASES = {"cerca": "Cerca de mi", "verificacion": "Verificacion", "pregunta": "Pregunta", "mapa": "Mapa", "ficha": "Ficha",
           "monitoreo": "Monitoreo", "vigilancia": "Vigilancia", "panorama": "Panorama"}


def init() -> None:
    if "goto" in st.session_state:  # pedido de cambio de vista desde un boton
        st.session_state.nav = st.session_state.pop("goto")
    if "nav" not in st.session_state:  # enlace directo: ?vista=cerca, ?vista=ficha&laguna=concepcion
        st.session_state.nav = ALIASES.get(st.query_params.get("vista", "").lower(), VIEWS[0])
        if st.query_params.get("laguna"):
            st.session_state.sel = st.query_params["laguna"]
    st.session_state.setdefault("sel", None)


def go(view: str, body_id: str | None = None) -> None:
    if body_id is not None:
        st.session_state.sel = body_id
    st.session_state.goto = view
    st.rerun()


def open_button(body_id: str, key: str, label: str = "Ver ficha") -> None:
    if st.button(label, key=key, width="stretch"):
        go("Ficha", body_id)
