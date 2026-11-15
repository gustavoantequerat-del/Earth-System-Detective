"""Vigilancia semanal: focos de calor NASA FIRMS en las cuencas de los cuerpos de agua en riesgo.

  python -m uma.alerts --project TU-PROYECTO            # revisa y avisa
  python -m uma.alerts --project TU-PROYECTO --dry-run  # revisa sin enviar avisos

Por cada cuerpo de agua vigilado cuenta los focos de calor FIRMS (MODIS y VIIRS, pixeles de 1 km) de los
ultimos 7 dias, cerca (subcuenca local) y en toda la cuenca de aporte, y los compara con la misma semana
de los 5 anos anteriores. Hay alerta operativa si:
  - el cuerpo de agua ya esta en riesgo (huella humana, alerta temprana o incalculable) y
  - hay al menos MIN_FOCOS focos y al menos el doble de lo normal para esa semana.

Guarda el resultado en data/real/alertas_semanales.json (lo muestra la app) y en la auditoria
(tabla operational_alerts de uma.db). Avisos opcionales, configurados con variables de entorno o un
archivo .env en la carpeta del proyecto (nunca subir .env a GitHub):
  Telegram: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
  Correo:   SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, ALERT_EMAIL_TO
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import smtplib
import sqlite3
import urllib.parse
import urllib.request
from email.message import EmailMessage
from pathlib import Path

import ee
import pandas as pd

from uma import gee_extract as gx
from uma.suspects_upstream import basin_geometry

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "real"
RISK = {"Huella humana", "Alerta temprana", "Incalculable", "Aguas arriba"}
MIN_FOCOS = 5
FACTOR = 2.0
BASE_YEARS = 5


def load_env():
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def fire_count(geom, start: ee.Date, days: int = 7) -> int:
    """Pixeles de 1 km con al menos un foco de calor en la ventana."""
    col = ee.ImageCollection("FIRMS").filterDate(start, start.advance(days, "day")).select("T21")
    img = col.max().gt(0).selfMask()
    v = gx.retry(lambda: img.reduceRegion(ee.Reducer.count(), geom, 1000, maxPixels=1e10, tileScale=4)
                 .get("T21").getInfo())
    return int(v or 0)


def check(body: dict, end: dt.date) -> dict:
    cfg = pd.read_csv(ROOT / "config" / "bodies.csv").set_index("body_id").loc[body["body_id"]]
    pt = ee.Geometry.Point([cfg.lon, cfg.lat])
    areas = {"cerca": gx.basin_for(pt).union(pt.buffer(float(cfg.radius_km) * 1000), 100)}
    if (DATA / "basins" / f"{body['body_id']}.geojson").exists():
        areas["cuenca"] = basin_geometry(body["body_id"])
    start = end - dt.timedelta(days=7)
    out = {"body_id": body["body_id"], "name": body["name"], "state": body["state"],
           "window": f"{start.isoformat()} a {end.isoformat()}", "areas": {}}
    for nm, geom in areas.items():
        now = fire_count(geom, ee.Date(start.isoformat()))
        past = [fire_count(geom, ee.Date(start.replace(year=start.year - k).isoformat())) for k in range(1, BASE_YEARS + 1)]
        normal = sum(past) / len(past)
        alert = body["state"] in RISK and now >= MIN_FOCOS and now >= FACTOR * max(normal, 1)
        out["areas"][nm] = {"focos": now, "normal": round(normal, 1), "alerta": bool(alert)}
    out["alerta"] = any(a["alerta"] for a in out["areas"].values())
    return out


def message(rows: list[dict], end: dt.date) -> str:
    al = [r for r in rows if r["alerta"]]
    lines = [f"Detector de huella humana - vigilancia semanal de incendios (NASA FIRMS), semana al {end.isoformat()}"]
    if not al:
        lines.append("Sin alertas: los focos de calor estan dentro de lo normal en las cuencas vigiladas.")
    for r in al:
        for nm, a in r["areas"].items():
            if a["alerta"]:
                lines.append(f"ALERTA {r['name']} ({r['state']}): {a['focos']} focos en la {nm} "
                             f"vs {a['normal']} normales para esta semana.")
    return "\n".join(lines)


def send_telegram(text: str) -> str:
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (tok and chat):
        return "telegram no configurado"
    data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    with urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage", data=data, timeout=30) as r:
        return f"telegram {r.status}"


def send_email(text: str) -> str:
    need = ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "ALERT_EMAIL_TO"]
    if not all(os.environ.get(k) for k in need):
        return "correo no configurado"
    msg = EmailMessage()
    msg["Subject"] = text.splitlines()[0]
    msg["From"] = os.environ["SMTP_USER"]
    msg["To"] = os.environ["ALERT_EMAIL_TO"]
    msg.set_content(text)
    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", 587)), timeout=30) as s:
        s.starttls()
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        s.send_message(msg)
    return "correo enviado"


def record(rows, end, sent):
    con = sqlite3.connect(DATA / "uma.db")
    con.execute("""CREATE TABLE IF NOT EXISTS operational_alerts (
        checked_at TEXT, week_end TEXT, body_id TEXT, state TEXT, area TEXT,
        fires INTEGER, normal REAL, alert INTEGER, notified TEXT)""")
    now = dt.datetime.now().isoformat(timespec="seconds")
    for r in rows:
        for nm, a in r["areas"].items():
            con.execute("INSERT INTO operational_alerts VALUES (?,?,?,?,?,?,?,?,?)",
                        (now, end.isoformat(), r["body_id"], r["state"], nm, a["focos"], a["normal"],
                         int(a["alerta"]), sent))
    con.commit()
    con.close()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--end", default="", help="ultimo dia de la semana (AAAA-MM-DD); por defecto ayer")
    a = ap.parse_args(argv)
    load_env()
    key = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if key and Path(key).exists():  # GitHub Actions u otro servidor: cuenta de servicio
        email = json.loads(Path(key).read_text())["client_email"]
        ee.Initialize(ee.ServiceAccountCredentials(email, key), project=a.project)
    else:                            # computadora con `earthengine authenticate`
        ee.Initialize(project=a.project)
    end = dt.date.fromisoformat(a.end) if a.end else dt.date.today() - dt.timedelta(days=1)
    results = json.loads((DATA / "results.json").read_text(encoding="utf-8"))
    controls = {r["control_id"] for r in results if r.get("control_id")}
    watch = [r for r in results if r["body_id"] not in controls or r["state"] in RISK]
    rows = []
    for r in watch:
        print(f"== {r['name']}", flush=True)
        c = check(r, end)
        print("   ", {k: v for k, v in c["areas"].items()}, "ALERTA" if c["alerta"] else "", flush=True)
        rows.append(c)
    text = message(rows, end)
    print("\n" + text)
    sent = "simulacro (--dry-run)"
    if not a.dry_run:
        sent = "; ".join([send_telegram(text), send_email(text)])
    print("\nAvisos:", sent)
    (DATA / "alertas_semanales.json").write_text(json.dumps(
        {"week_end": end.isoformat(), "checked_at": dt.datetime.now().isoformat(timespec="seconds"),
         "notified": sent, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    record(rows, end, sent)


if __name__ == "__main__":
    main()
