"""Resumen del rio por tramos para la web (Next.js).

  python -m uma.river_summary            # lee data/real/rio_tramos.* y escribe data/real/rio_resumen.json

Toma lo que mide `uma/rivers.py` (agua en el cauce, verde en epoca seca, represas, cultivos e inventario de
OpenStreetMap) y arma un JSON listo para graficar, con la prueba de desvio entre tramos (Mann-Kendall con correccion
de Hamed y Rao y pendiente de Theil-Sen, igual que la vista Streamlit) y una lista de controles de calidad de los datos.
No necesita Earth Engine.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from uma.monthly_model import modified_mk
from uma.river_reaches import FEEDS, REACHES, RIVER_INFLOW

ROOT = Path(__file__).resolve().parent.parent
BASE = (1985, 2000)          # periodo de referencia
RECENT = 5                   # ultimos anos comparados
PAIRS = [("T1", "T2"), ("T2", "T3"), ("T3", "T4"), ("T4", "T5")]
MIN_BASE_HA = 50             # por debajo, un porcentaje de cambio no es informativo
LAKES = {"uru_uru": "Lago Uru Uru", "poopo": "Lago Poopó"}
NAMES = {"T1": "Salida del Titicaca a Nazacara", "T2": "Nazacara a Calacoto", "T3": "Calacoto a Ulloma",
         "T4": "Ulloma a Chuquina", "T5": "Chuquina a Uru Uru", "T6": "Uru Uru a Poopó",
         "M": "Río Mauri (afluente desde Perú)"}
KINDS = ["Canal o acequia", "Represa o toma", "Reservorio", "Mina o cantera", "Planta de tratamiento", "Piletas de sal"]


def _r(x, nd=1):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(float(x), nd)


def _pivot(df: pd.DataFrame, var: str) -> pd.DataFrame:
    return df[df["var"] == var].pivot(index="year", columns="reach", values="value").sort_index()


def _change(d: pd.DataFrame, reach: str) -> dict:
    s = d[reach].dropna()
    base = s.loc[BASE[0]:BASE[1]].mean()
    last = s.iloc[-RECENT:].mean()
    pct = 100 * (last - base) / base if base >= MIN_BASE_HA else None
    return {"base": _r(base), "recent": _r(last), "delta": _r(last - base), "pct": _r(pct, 0)}


def diversion(water: pd.DataFrame, green: pd.DataFrame, osm: list[dict]) -> list[dict]:
    """El tramo de abajo deberia tener agua en proporcion al de arriba (ajuste 1985-2000). Si con los anos llega cada
    vez menos de lo esperado (MK corregido p<0.05 y al menos -10%) y al costado crece el verde en la seca o hay canales,
    es la huella de un desvio."""
    g = green.reindex(water.index).interpolate(limit_direction="both")
    rows = []
    for a, b in PAIRS:
        base = water.loc[:BASE[1]]
        k = np.polyfit(base[a], base[b], 1)
        res = (water[b] - np.polyval(k, water[a])) / base[b].mean()
        mk = modified_mk(res.values)
        slope = stats.theilslopes(res.values, res.index)[0]
        pct = slope * (res.index[-1] - res.index[0]) * 100
        canals = sum(1 for x in osm if x["reach"] == b and x["kind"] in ("Canal o acequia", "Represa o toma"))
        dg = g[b].iloc[-RECENT:].mean() - g[b].loc[:BASE[1]].mean()
        sign = mk["p"] < 0.05 and pct < -10
        verdict = ("Posible desvío" if sign and (dg > 50 or canals) else "Pierde agua, sin señal de riego" if sign
                   else "Sin pérdida significativa")
        rows.append({"from": a, "to": b, "to_name": NAMES[b], "missing_pct": _r(pct, 0), "p": _r(mk["p"], 3),
                     "n_eff": mk["n_eff"], "green_delta_ha": _r(dg, 0), "canals": canals, "verdict": verdict,
                     "expected": [_r(v) for v in np.polyval(k, water[a]).tolist()],
                     "observed": [_r(v) for v in water[b].tolist()]})
    return rows


def quality(df: pd.DataFrame, gj: dict, osm: list[dict], results: list[dict]) -> list[dict]:
    """Controles automaticos. Cada uno dice que se reviso y si paso."""
    checks = []
    years = sorted(df.year.unique())
    full = list(range(years[0], years[-1] + 1))
    dup = int(df.duplicated(["reach", "year", "var"]).sum())
    neg = int((df.value < 0).sum())
    checks.append({"label": "Registros únicos y sin valores negativos", "ok": dup == 0 and neg == 0,
                   "detail": f"{len(df):,} registros; {dup} duplicados y {neg} valores negativos."})
    gaps = {}
    for var in ["water_ha", "green_ha", "artificial_ha", "crop_ha"]:
        have = set(df[df["var"] == var].year)
        miss = [y for y in full if y not in have]
        if miss:
            gaps[var] = miss
    checks.append({"label": "Años completos 1985–2024", "ok": not gaps or set(gaps) == {"green_ha"},
                   "warn": bool(gaps),
                   "detail": "Sin huecos." if not gaps else
                   "; ".join(f"{v}: falta {', '.join(map(str, m))}" for v, m in gaps.items()) +
                   " (sin mosaico Landsat de junio a octubre; en los gráficos se interpola y se marca)."})
    green = _pivot(df, "green_ha")
    zero_first = [r for r in green.columns if green[r].iloc[0] == 0 and green[r].iloc[1:6].mean() > 50]
    checks.append({"label": "Cobertura Landsat del primer año", "ok": True, "warn": bool(zero_first),
                   "detail": "Sin anomalías." if not zero_first else
                   f"1985 marca 0 ha verdes en {', '.join(zero_first)} con valores altos en los años siguientes: "
                   "es falta de imágenes, no ausencia de riego. La referencia 1985-2000 promedia 16 años y "
                   "amortigua este efecto."})
    # continuidad de la geometria del cauce
    feats = {f["properties"]["reach"]: f for f in gj["features"]}
    breaks = []
    for a, b in [("T1", "T2"), ("T2", "T3"), ("T3", "T4"), ("T4", "T5")]:
        end = feats[a]["geometry"]["coordinates"][-1][-1]
        start = feats[b]["geometry"]["coordinates"][0][0]
        if math.dist(end, start) > 0.01:
            breaks.append(f"{a}-{b}")
    checks.append({"label": "Cauce continuo de T1 a T5 (HydroSHEDS)", "ok": not breaks,
                   "detail": "Cada tramo empieza donde termina el anterior." if not breaks else
                   "Cortes en " + ", ".join(breaks)})
    # el resumen coincide con lo que usa el motor
    by = {r["body_id"]: r for r in results}
    for bid, (reach, _) in RIVER_INFLOW.items():
        r = by.get(bid)
        ok = bool(r and r.get("state") == "Aguas arriba")
        checks.append({"label": f"El motor usa el tramo {reach} como entrada de {LAKES.get(bid, bid)}", "ok": ok,
                       "detail": f"Veredicto publicado: {r['state'] if r else 'sin resultado'}."})
    urban = sum(1 for x in osm if x["kind"] == "Canal o acequia" and x.get("lake") == "uru_uru" and not x.get("reach"))
    checks.append({"label": "Inventario OpenStreetMap", "ok": True, "warn": True,
                   "detail": f"{len(osm):,} elementos. {urban} canales cerca de Uru Uru no tocan el río: muchos son "
                             "desagües de la ciudad de Oruro. OpenStreetMap es colaborativo y puede estar incompleto."})
    return checks


def build(data_dir: Path) -> dict:
    df = pd.read_csv(data_dir / "rio_tramos.csv")
    gj = json.loads((data_dir / "rio_tramos.geojson").read_text(encoding="utf-8"))
    osm = json.loads((data_dir / "rio_osm.json").read_text(encoding="utf-8"))
    results = json.loads((data_dir / "results.json").read_text(encoding="utf-8"))
    water, green, art, crop = (_pivot(df, v) for v in ["water_ha", "green_ha", "artificial_ha", "crop_ha"])
    props = {f["properties"]["reach"]: f["properties"] for f in gj["features"]}
    order = [r for r, *_ in REACHES] + ["M"]

    reaches = []
    for rid in order:
        p = props.get(rid, {})
        reaches.append({
            "id": rid, "name": NAMES[rid], "km": p.get("km"),
            "consumptive_use_pct": p.get("uso_consuntivo_pct"), "regulation_pct": p.get("regulacion_pct"),
            "water": _change(water, rid), "green": _change(green, rid),
            "artificial": _change(art, rid), "crops": _change(crop, rid),
            "osm": {k: sum(1 for x in osm if x["reach"] == rid and x["kind"] == k) for k in KINDS},
        })

    years = [int(y) for y in water.index]
    g_interp = green.reindex(water.index).interpolate(limit_direction="both")
    series = {rid: {"water": [_r(v) for v in water[rid].tolist()],
                    "green": [_r(v) for v in green.reindex(water.index)[rid].tolist()],
                    "green_filled": [_r(v) for v in g_interp[rid].tolist()]} for rid in order}

    by = {r["body_id"]: r for r in results}
    lakes = []
    for bid, rids in FEEDS.items():
        r = by.get(bid, {})
        gb = sum(green[x].loc[BASE[0]:BASE[1]].mean() for x in rids)
        gl = sum(green[x].dropna().iloc[-RECENT:].mean() for x in rids)
        near = [x for x in osm if x["reach"] in rids or x["lake"] == bid]
        split = r.get("upstream_split") or {}
        dec = r.get("decomposition_ha") or {}
        lakes.append({
            "id": bid, "name": r.get("name", LAKES[bid]), "reaches": rids,
            "state": r.get("state"), "confidence": r.get("confidence"),
            "change_pct": _r((r.get("trend") or {}).get("change_pct"), 0),
            "climate_share": _r(r.get("climate_share"), 2),
            "upstream_source": r.get("upstream_source"), "upstream_split": split or None,
            "decomposition_ha": {k: _r(v, 0) for k, v in dec.items()},
            "robustness": r.get("robustness"), "why": r.get("why", []),
            "green_base_ha": _r(gb, 0), "green_recent_ha": _r(gl, 0),
            "osm": {k: sum(1 for x in near if x["kind"] == k) for k in KINDS},
        })

    feats = [{"reach": f["properties"]["reach"], "name": NAMES.get(f["properties"]["reach"], f["properties"]["name"]),
              "paths": [[[round(c[0], 4), round(c[1], 4)] for c in line] for line in f["geometry"]["coordinates"]]}
             for f in gj["features"]]
    points = [{"kind": x["kind"], "name": x["name"], "lat": x["lat"], "lon": x["lon"], "reach": x["reach"],
               "lake": x["lake"], "dist_river_km": x["dist_rio_km"], "url": x["osm"]} for x in osm]

    return {
        "generated": date.today().isoformat(),
        "period": {"base": list(BASE), "recent": [years[-RECENT], years[-1]], "years": [years[0], years[-1]]},
        "years": years, "reaches": reaches, "series": series, "lakes": lakes,
        "diversion": diversion(water, green, osm), "geometry": feats, "osm_points": points,
        "osm_totals": {k: sum(1 for x in osm if x["kind"] == k) for k in KINDS},
        "quality": quality(df, gj, osm, results),
        "sources": [
            {"name": "MapBiomas Agua Bolivia (colección 2)", "use": "Agua en el cauce y represas, franja de 1 km",
             "url": "https://bolivia.mapbiomas.org/"},
            {"name": "Landsat 5, 7, 8 y 9 (USGS/NASA)", "use": "Verde en época seca (NDVI > 0,3, junio a octubre), franja de 5 km",
             "url": "https://landsat.gsfc.nasa.gov/"},
            {"name": "HydroSHEDS Free Flowing Rivers (Grill et al. 2019)", "use": "Trazado del cauce, uso consuntivo y regulación",
             "url": "https://www.hydrosheds.org/"},
            {"name": "OpenStreetMap", "use": "Canales, tomas, represas, minas y plantas de tratamiento",
             "url": "https://www.openstreetmap.org/"},
        ],
    }


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    data_dir = Path(argv[0]) if argv else ROOT / "data" / "real"
    out = build(data_dir)
    (data_dir / "rio_resumen.json").write_text(json.dumps(out, ensure_ascii=False, allow_nan=False, separators=(",", ":")),
                                               encoding="utf-8")
    for d in out["diversion"]:
        print(f"{d['from']}->{d['to']}: {d['missing_pct']}% p={d['p']} verde {d['green_delta_ha']} ha "
              f"canales {d['canals']} -> {d['verdict']}")
    for q in out["quality"]:
        print("OK " if q["ok"] and not q.get("warn") else "AVISO" if q["ok"] else "FALLA", q["label"], "-", q["detail"])


if __name__ == "__main__":
    main()
