"""Explicaciones en lenguaje sencillo con Claude, ancladas a los datos del detector.

Claude solo recibe los resultados ya calculados (veredicto, motivos, pruebas, sospechosos, rio, proteccion) y debe
explicar con esos numeros, sin inventar. Sin clave de API, la app usa una explicacion armada con plantillas a
partir de los mismos datos, asi que siempre hay una explicacion.

Clave: ANTHROPIC_API_KEY en .streamlit/secrets.toml, en los secretos de Streamlit Cloud o en .env.
"""
from __future__ import annotations

import json
import os
from typing import Iterator

import streamlit as st

import data

MODEL = "claude-opus-5-5"
LANGS = {"Espanol": "espanol de Bolivia, sencillo", "Quechua": "quechua boliviano (runasimi), con una linea final "
         "en espanol que resuma lo principal", "Aymara": "aymara, con una linea final en espanol que resuma lo "
         "principal", "English": "plain English"}
SPEECH = {"Espanol": "es-ES", "English": "en-US", "Quechua": "es-ES", "Aymara": "es-ES"}

SYSTEM = """Eres el explicador del "Detector de huella humana", una herramienta que analiza por que se pierde el
agua de lagos y lagunas de Bolivia con datos satelitales de la NASA y otras fuentes.

Tu publico: cualquier persona, incluidas personas sin estudios tecnicos, dirigentes comunales, periodistas y
autoridades locales. Habla claro, con frases cortas y ejemplos cotidianos. Si usas una palabra tecnica, explicala
en la misma frase.

Reglas:
- Usa solo los datos que vienen dentro de <datos>. Si algo no esta ahi, di que el detector no lo sabe. No
  inventes cifras, lugares, empresas ni culpables.
- Siempre di que tan seguro esta el detector (su confianza) y por que. Si la confianza es baja, dilo sin rodeos.
- El detector muestra coincidencias y consistencia en el tiempo, no prueba causalidad estricta: no digas que algo
  esta "probado".
- "Aguas arriba" significa que a la laguna le llega menos agua por el rio que la alimenta; explica de donde viene
  ese rio y que dice el detector de esa fuente.
- Si hay un rango (por ejemplo "entre 0 y 88,000 ha"), explica por que es un rango y que dato haria falta para
  cerrarlo.
- Cierra con una o dos acciones concretas que una comunidad o una autoridad podria tomar, sacadas de los datos.
- Largo: unas 150 a 220 palabras, salvo que te pidan mas o menos. Sin tablas.
"""


def api_key() -> str | None:
    try:
        if "ANTHROPIC_API_KEY" in st.secrets:
            return str(st.secrets["ANTHROPIC_API_KEY"])
    except Exception:  # sin archivo de secretos
        pass
    if not os.environ.get("ANTHROPIC_API_KEY"):
        env = data.ROOT / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("ANTHROPIC_API_KEY="):
                    os.environ["ANTHROPIC_API_KEY"] = line.split("=", 1)[1].strip().strip('"')
    return os.environ.get("ANTHROPIC_API_KEY")


def available() -> bool:
    return bool(api_key())


# ------------------------------------------------------------------ contexto
def body_context(r: dict) -> dict:
    """Lo que Claude necesita saber de un cuerpo de agua, sin series largas."""
    sus = [{"sospechoso": s["label"], "evidencia": s["evidence"], "crece_desde": s.get("onset"),
            "antecede_la_caida": s.get("precedes"), "indirecto": s.get("indirect", False)}
           for s in r["suspects"] if s["evidence"] != "debil"][:6]
    out = {"nombre": r["name"], "departamento": r.get("department"), "veredicto": r["state"],
           "confianza": r["confidence"], "pruebas_superadas": f"{r['n_pass']} de 3",
           "cambio_del_agua_pct": round(r["trend"]["change_pct"]),
           "periodo": "promedio 1985-2000 contra los ultimos 5 anos",
           "reparto_del_cambio_ha": r["decomposition_ha"], "motivos": r.get("why", []),
           "pruebas": {k: {"paso": t["pass"], "detalle": t["detail"]} for k, t in r["tests"].items()},
           "sospechosos_con_evidencia": sus, "proteccion": data.protection(r["body_id"])}
    for k in ("upstream_source", "upstream_split"):
        if r.get(k):
            out[k] = r[k]
    fire = data.fires_for(r["body_id"])
    if fire:
        out["incendios_semana"] = {"ventana": fire["window"], "alerta": fire["alerta"],
                                   "focos": {n: a["focos"] for n, a in fire["areas"].items()}}
    riv = river_summary(r["body_id"])
    if riv:
        out["rio"] = riv
    return out


def river_summary(body_id: str) -> dict | None:
    from views import rio
    if not rio.available(body_id):
        return None
    df = data.csv_file(data.DATA / "rio_tramos.csv")
    rids = rio.FEEDS[body_id]
    df = df[df.reach.isin(rids)]

    def chg(var):
        p = df[df["var"] == var].pivot(index="year", columns="reach", values="value")
        return {r: [round(p.loc[1985:2000, r].mean()), round(p[r].iloc[-5:].mean())] for r in p}
    osm = data.json_file(data.DATA / "rio_osm.json") or []
    near = [x for x in osm if x["reach"] in rids or x["lake"] == body_id]
    named = sorted({f"{x['kind']}: {x['name']}" for x in near if x["name"]})[:15]
    return {"agua_en_el_cauce_ha_[1985-2000, ultimos5]": chg("water_ha"),
            "verde_en_epoca_seca_ha_[1985-2000, ultimos5]": chg("green_ha"),
            "tramos": {f["properties"]["reach"]: f["properties"]["name"]
                       for f in (data.json_file(data.DATA / "rio_tramos.geojson") or {"features": []})["features"]},
            "openstreetmap_conteo": {k: sum(1 for x in near if x["kind"] == k) for k in sorted({x["kind"] for x in near})},
            "openstreetmap_con_nombre": named}


def overview_context(results: list[dict], national: list[dict]) -> dict:
    states: dict[str, int] = {}
    for n in national:
        states[n["state"]] = states.get(n["state"], 0) + 1
    ver = data.json_file(data.DATA / "verificacion.json") or {}
    return {"analisis_completos": [{"nombre": r["name"], "veredicto": r["state"], "confianza": r["confidence"],
                                    "cambio_pct": round(r["trend"]["change_pct"]),
                                    "reparto_ha": r["decomposition_ha"], "motivos": r.get("why", [])[:3],
                                    **({"fuente": r["upstream_source"]["name"], "rango_humano_aguas_arriba":
                                        r.get("upstream_split")} if r.get("upstream_source") else {})}
                                   for r in results],
            "barrido_nacional_300_lagunas": states,
            "agua_de_bolivia_2024_vs_media_pct": (ver.get("bolivia") or {}).get("2024_vs_media_pct"),
            "fuentes": "Landsat (NASA/USGS), NASA POWER, NASA FIRMS, MODIS, GRACE, CHIRPS, ERA5-Land, MapBiomas, "
                       "JRC, Hansen, WDPA, HydroSHEDS, OpenStreetMap"}


# ------------------------------------------------------------------ Claude
def stream(question: str, context: dict, lang: str = "Espanol", history: list[dict] | None = None) -> Iterator[str]:
    """Respuesta de Claude en partes (para st.write_stream). Si falla, explica por que en una linea."""
    import anthropic
    client = anthropic.Anthropic(api_key=api_key())
    system = [{"type": "text", "text": SYSTEM},
              {"type": "text", "text": "<datos>\n" + json.dumps(context, ensure_ascii=False, default=str) + "\n</datos>",
               "cache_control": {"type": "ephemeral"}}]
    messages = list(history or []) + [
        {"role": "user", "content": f"{question}\n\nResponde en {LANGS.get(lang, LANGS['Espanol'])}."}]
    try:
        with client.beta.messages.stream(
            model=MODEL, max_tokens=4000, system=system, messages=messages,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        ) as s:
            yield from s.text_stream
            final = s.get_final_message()
        if final.stop_reason == "refusal":
            yield "\n\n_(El modelo no respondio a esta pregunta. Proba con otra forma de preguntarlo.)_"
        elif final.stop_reason == "max_tokens":
            yield "\n\n_(Respuesta cortada por largo.)_"
    except anthropic.AuthenticationError:
        yield "La clave de API de Anthropic no es valida. Revisa ANTHROPIC_API_KEY."
    except anthropic.RateLimitError:
        yield "Hay muchas consultas en este momento. Proba de nuevo en un minuto."
    except anthropic.APIStatusError as e:
        yield f"El servicio de IA respondio con un error ({e.status_code}). Proba de nuevo mas tarde."
    except anthropic.APIConnectionError:
        yield "No hay conexion con el servicio de IA."


# ------------------------------------------------------------------ sin clave: plantilla
def plain_summary(r: dict) -> str:
    """Explicacion sencilla armada solo con los datos (sin IA)."""
    name = r["name"].split(" (")[0]
    chg = r["trend"]["change_pct"]
    conf = r["confidence"].lower()
    lines = [f"**{name}** tiene hoy {abs(chg):.0f}% {'menos' if chg < 0 else 'mas'} agua que en 1985-2000."]
    st_ = r["state"]
    if st_ == "Huella humana":
        top = next((s for s in r["suspects"] if not s.get("indirect") and s["evidence"] != "debil"), None)
        lines.append("El detector encuentra senales de que la actividad humana tiene que ver"
                     + (f": {top['label'].lower()} empezo a crecer en {top['onset']}, antes de que bajara el agua."
                        if top else "."))
    elif st_ == "Aguas arriba":
        src = r.get("upstream_source", {})
        sp = r.get("upstream_split") or {}
        lines.append(f"La causa principal esta aguas arriba: le llega menos agua por el rio desde "
                     f"{src.get('name', 'su fuente')}.")
        if sp:
            lines.append(f"De esa agua que no llega ({sp['upstream_ha']:,} ha), la parte humana va de "
                         f"{sp['human_min_ha']:,} a {sp['human_max_ha']:,} ha; para saberlo mejor hacen falta "
                         "mediciones del nivel del Titicaca y del caudal del rio.")
    elif st_ == "Causa climatica":
        lines.append("La mayor parte de la perdida se explica por menos lluvia y mas evaporacion.")
    elif st_ == "Incalculable":
        lines.append("El agua baja, pero con los datos disponibles no se puede decir por que.")
    elif st_ == "Alerta temprana":
        lines.append("Todavia no pierde agua, pero crece la presion humana alrededor.")
    else:
        lines.append("No muestra una perdida importante.")
    lines.append(f"El detector esta {('bastante seguro' if conf == 'alta' else 'medianamente seguro' if conf == 'media' else 'poco seguro')} "
                 f"(confianza {conf}, {r['n_pass']} de 3 pruebas).")
    if r.get("why"):
        lines.append("Lo importante: " + r["why"][0])
    prot = data.protection(r["body_id"])
    if prot["ramsar"]:
        lines.append(f"Es parte del sitio Ramsar {prot['ramsar']}, un humedal de importancia internacional.")
    return " ".join(lines)


def speak_button(text: str, lang: str = "Espanol") -> None:
    """Boton que lee el texto en voz alta con la voz del navegador (sin enviar nada a internet)."""
    import html as _h
    clean = text.replace("**", "").replace("_", "")
    st.iframe(f"""
<button id="b" style="border:none;border-radius:999px;padding:8px 16px;font-weight:800;cursor:pointer;
 background:#a5b4fc;color:#121528;font-family:sans-serif">Escuchar</button>
<div id="t" style="display:none">{_h.escape(clean)}</div>
<script>
const b=document.getElementById('b');let on=false;
b.onclick=()=>{{const s=window.speechSynthesis;if(on){{s.cancel();on=false;b.textContent='Escuchar';return;}}
 const u=new SpeechSynthesisUtterance(document.getElementById('t').textContent);u.lang='{SPEECH.get(lang, 'es-ES')}';
 u.rate=0.95;u.onend=()=>{{on=false;b.textContent='Escuchar';}};s.speak(u);on=true;b.textContent='Detener';}};
</script>""", height=50)
