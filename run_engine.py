"""Corre el motor sobre una carpeta de CSV y escribe results.json para la app.

Uso:
  python run_engine.py                 # datos de prueba (data/sample)
  python run_engine.py data/real 2005  # CSV reales, periodo base hasta 2005
"""
import argparse
import json
import math
from pathlib import Path

import pandas as pd

from uma import engine

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("source", nargs="?", type=Path, default=root / "data" / "sample")
parser.add_argument("baseline_end", nargs="?", type=int, default=2000)
parser.add_argument("note", nargs="?", default="")
parser.add_argument("--conservative", action="store_true", help="Genera el modelo conservador en la subcarpeta validation.")
args = parser.parse_args()
src, baseline_end, note = args.source, args.baseline_end, args.note

if src.name == "sample" and not (src / "series.csv").exists():
    from uma import synthetic
    synthetic.build(src)

bodies = pd.read_csv(src / "bodies.csv", dtype={"control_id": str}).fillna({"control_id": ""})
if (src / "basins.csv").exists():  # que cuerpos de agua reciben agua por rio de otro de la lista
    up = pd.read_csv(src / "basins.csv", dtype={"upstream_bodies": str}).fillna("")[["body_id", "upstream_bodies"]]
    bodies = bodies.merge(up, on="body_id", how="left").fillna({"upstream_bodies": ""})
series = pd.read_csv(src / "series.csv")
suspects = pd.read_csv(src / "suspects.csv") if (src / "suspects.csv").exists() else \
    pd.DataFrame(columns=["body_id", "year", "suspect", "value"])

def safe_json(value):
    if isinstance(value, dict):
        return {k: safe_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [safe_json(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


results = safe_json(engine.run(bodies, series, suspects, baseline_end, conservative=args.conservative))
output = src / "validation" if args.conservative else src
output.mkdir(exist_ok=True)
(output / "results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False, allow_nan=False), encoding="utf-8")

from uma import audit
audit.record_run(output, results, baseline_end, note, input_dir=src)
if args.conservative:
    from uma import report
    report.write(src, bodies, series, suspects, results, baseline_end)

def yn(v):
    return "n/e" if v is None else ("si" if v else "no")


for r in results:
    t = r["tests"]
    print(f"{r['body_id']:8} {r['state']:16} confianza {r['confidence']:5} "
          f"clima={yn(t['clima']['pass'])} control={yn(t['control']['pass'])} "
          f"coincidencia={yn(t['coincidencia']['pass'])}  "
          f"cambio {r['trend']['change_pct']:+.0f}%  sospechoso: {r['suspects'][0]['label'] if r['suspects'] else '-'}")
print(f"\nEscrito {output / 'results.json'}")
