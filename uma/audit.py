"""Registro de auditoria de Uma en SQLite (data/<carpeta>/uma.db).

Cada corrida del motor se agrega sin borrar las anteriores, con la huella (sha256) de los datos de
entrada y del codigo, los parametros y una nota. Asi cualquier veredicto puede rastrearse y repetirse.

Tablas: runs, verdicts, evidence, suspects, alerts, reviews.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  note TEXT,
  baseline_end INTEGER,
  params_json TEXT,
  datasets_json TEXT,
  inputs_sha256 TEXT,
  code_sha256 TEXT
);
CREATE TABLE IF NOT EXISTS verdicts (
  run_id INTEGER REFERENCES runs(run_id),
  body_id TEXT, name TEXT, control_id TEXT,
  state TEXT, confidence TEXT, n_pass INTEGER,
  change_pct REAL, sen_ha_per_year REAL, trend_p REAL, climate_r2 REAL,
  decomposition_json TEXT,
  PRIMARY KEY (run_id, body_id)
);
CREATE TABLE IF NOT EXISTS evidence (
  run_id INTEGER, body_id TEXT, test TEXT, passed INTEGER, p REAL, detail TEXT,
  PRIMARY KEY (run_id, body_id, test)
);
CREATE TABLE IF NOT EXISTS suspects (
  run_id INTEGER, body_id TEXT, suspect TEXT, label TEXT, evidence TEXT,
  onset INTEGER, rho REAL, p REAL, precedes INTEGER, rank INTEGER,
  PRIMARY KEY (run_id, body_id, suspect)
);
CREATE TABLE IF NOT EXISTS alerts (
  alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
  body_id TEXT, state TEXT, opened_run INTEGER, opened_at TEXT,
  closed_run INTEGER, closed_at TEXT, status TEXT DEFAULT 'abierta'
);
CREATE TABLE IF NOT EXISTS reviews (
  review_id INTEGER PRIMARY KEY AUTOINCREMENT,
  body_id TEXT, run_id INTEGER, created_at TEXT,
  reviewer TEXT, outcome TEXT, comment TEXT
);
CREATE TABLE IF NOT EXISTS diagnostics (
  run_id INTEGER, body_id TEXT, diagnostics_json TEXT,
  PRIMARY KEY (run_id, body_id)
);
"""

DATASETS = {
    "agua": "Landsat 5/7/8/9 C2 L2 (MNDWI epoca seca); validacion JRC/GSW1_4/YearlyHistory",
    "clima": "NASA POWER PRECTOTCORR y T2M promediados en la cuenca de aporte (HydroBASINS nivel 8)",
    "el_nino": "NOAA CPC ONI",
    "sospechosos": "En dos escalas, cerca (subcuenca local) y cuenca de aporte: MapBiomas Bolivia col. 2, Hansen GFC 2025 v1.13, MODIS MCD64A1, "
                   "DMSP-OLS + VIIRS V21/V22, WorldPop, Landsat NDVI",
    "agua_subterranea": "NASA GRACE/GRACE-FO MASCON",
}
ALERT_STATES = {"Huella humana", "Alerta temprana", "Indicios de intervencion humana",
                "Evidencia reforzada de intervencion", "Perdida no explicada"}
CODE_FILES = ["engine.py", "gee_extract.py", "nasa_power.py", "upstream.py", "suspects_upstream.py",
              "twins.py", "climate_blend.py", "hydro_extra.py"]


def connect(data_dir: Path) -> sqlite3.Connection:
    con = sqlite3.connect(Path(data_dir) / "uma.db")
    con.executescript(SCHEMA)
    return con


def _sha(paths) -> str:
    h = hashlib.sha256()
    for p in sorted(paths):
        p = Path(p)
        if p.exists():
            h.update(p.name.encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


def record_run(data_dir: Path, results: list[dict], baseline_end: int, note: str = "",
               params: dict | None = None, created_at: str | None = None, *, input_dir: Path | None = None) -> int:
    data_dir = Path(data_dir)
    inputs = Path(input_dir) if input_dir is not None else data_dir
    con = connect(data_dir)
    now = created_at or dt.datetime.now().isoformat(timespec="seconds")
    from uma import engine
    settings = {"alpha": engine.ALPHA, "min_effect_pct": engine.MIN_EFFECT_PCT,
                "max_lag_years": engine.MAX_LAG_YEARS}
    code_paths = [ROOT / "uma" / f for f in CODE_FILES] + [ROOT / "run_engine.py"]
    if any(r.get("method_version") for r in results):
        from uma.validation import policy
        settings["evidence_policy"] = policy()
        code_paths.extend([ROOT / "uma/validation.py", ROOT / "uma/safeguarded.py", ROOT / "config/evidence_policy.json"])
    settings.update(params or {})
    cur = con.execute(
        "INSERT INTO runs(created_at, note, baseline_end, params_json, datasets_json, inputs_sha256, code_sha256) "
        "VALUES (?,?,?,?,?,?,?)",
        (now, note, baseline_end, json.dumps(settings), json.dumps(DATASETS, ensure_ascii=False),
         _sha([inputs / f for f in ("bodies.csv", "series.csv", "suspects.csv", "basins.csv")]), _sha(code_paths)))
    run_id = cur.lastrowid
    for r in results:
        if r.get("method_version"):
            keys = ("selected_model", "model_comparison", "model_validation", "quality", "control_validation",
                    "backtest", "independent_evidence", "method_version")
            con.execute("INSERT INTO diagnostics VALUES (?,?,?)", (
                run_id, r["body_id"], json.dumps({k: r.get(k) for k in keys}, ensure_ascii=False)))
        con.execute("INSERT INTO verdicts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
            run_id, r["body_id"], r["name"], r.get("control_id"), r["state"], r["confidence"], r["n_pass"],
            r["trend"]["change_pct"], r["trend"]["sen_ha_per_year"], r["trend"]["p"], r["climate_r2"],
            json.dumps(r["decomposition_ha"], ensure_ascii=False)))
        for k, t in r["tests"].items():
            con.execute("INSERT INTO evidence VALUES (?,?,?,?,?,?)",
                        (run_id, r["body_id"], k, None if t["pass"] is None else int(t["pass"]), t.get("p"), t["detail"]))
        for i, s in enumerate(r["suspects"]):
            con.execute("INSERT INTO suspects VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (run_id, r["body_id"], s["suspect"], s["label"], s["evidence"], s["onset"],
                         s["rho"], s["p"], int(s["precedes"]), i + 1))
        # alertas: se abren al entrar en huella humana o alerta temprana y se cierran al salir
        open_ = con.execute("SELECT alert_id FROM alerts WHERE body_id=? AND closed_run IS NULL",
                            (r["body_id"],)).fetchone()
        if r["state"] in ALERT_STATES and not open_:
            con.execute("INSERT INTO alerts(body_id, state, opened_run, opened_at) VALUES (?,?,?,?)",
                        (r["body_id"], r["state"], run_id, now))
        elif r["state"] not in ALERT_STATES and open_:
            con.execute("UPDATE alerts SET closed_run=?, closed_at=?, status='cerrada' WHERE alert_id=?",
                        (run_id, now, open_[0]))
    con.commit()
    con.close()
    return run_id


def history(data_dir: Path, body_id: str):
    import pandas as pd
    con = connect(data_dir)
    q = """SELECT r.run_id AS corrida, r.created_at AS fecha, v.state AS estado, v.confidence AS confianza,
                  v.n_pass AS pruebas, ROUND(v.change_pct) AS cambio_pct, v.control_id AS gemela,
                  r.note AS nota, r.inputs_sha256 AS huella_datos, r.code_sha256 AS huella_codigo
           FROM verdicts v JOIN runs r USING(run_id) WHERE v.body_id=? ORDER BY r.run_id DESC"""
    df = pd.read_sql(q, con, params=(body_id,))
    rv = pd.read_sql("SELECT created_at AS fecha, reviewer AS revisor, outcome AS resultado, comment AS comentario "
                     "FROM reviews WHERE body_id=? ORDER BY review_id DESC", con, params=(body_id,))
    al = pd.read_sql("SELECT state AS estado, opened_at AS abierta, closed_at AS cerrada, status AS situacion "
                     "FROM alerts WHERE body_id=? ORDER BY alert_id DESC", con, params=(body_id,))
    con.close()
    return df, rv, al


def add_review(data_dir: Path, body_id: str, reviewer: str, outcome: str, comment: str):
    con = connect(data_dir)
    last = con.execute("SELECT MAX(run_id) FROM runs").fetchone()[0]
    con.execute("INSERT INTO reviews(body_id, run_id, created_at, reviewer, outcome, comment) VALUES (?,?,?,?,?,?)",
                (body_id, last, dt.datetime.now().isoformat(timespec="seconds"), reviewer, outcome, comment))
    con.commit()
    con.close()
