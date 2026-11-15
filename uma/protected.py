"""Que cuerpos de agua estan en areas protegidas o en sitios Ramsar (humedales de importancia internacional).

  python -m uma.protected --project TU-PROYECTO

Fuente: WDPA (UNEP-WCMC), en Earth Engine. Las areas protegidas se cruzan con sus poligonos. Los sitios
Ramsar de Bolivia figuran en WDPA solo como puntos con su superficie: se aproximan como un circulo de esa
superficie alrededor del punto, y se marcan como aproximados.
Salida: data/real/protegidas.json y data/national/protegidas.json  ({body_id: {...}})
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import ee
import pandas as pd

from uma.gee_extract import retry

ROOT = Path(__file__).resolve().parent.parent


def ramsar_sites() -> list[dict]:
    pts = ee.FeatureCollection("WCMC/WDPA/current/points").filter(ee.Filter.stringContains("DESIG_ENG", "Ramsar")) \
        .filterBounds(ee.Geometry.Rectangle([-71, -24, -56, -9]))
    out = []
    for f in retry(lambda: pts.getInfo())["features"]:
        p = f["properties"]
        lon, lat = f["geometry"]["coordinates"]
        out.append({"name": p["NAME"], "lat": lat, "lon": lon, "radius_km": math.sqrt(float(p["REP_AREA"]) / math.pi)})
    return out


def protected_areas(points: pd.DataFrame) -> dict[str, list[str]]:
    """Nombres de las areas protegidas (poligonos WDPA) que contienen cada punto."""
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([r.lon, r.lat]), {"id": r.id}) for r in points.itertuples()])
    wdpa = ee.FeatureCollection("WCMC/WDPA/current/polygons").filterBounds(ee.Geometry.Rectangle([-71, -24, -56, -9]))
    joined = ee.Join.saveAll("pa").apply(fc, wdpa, ee.Filter.intersects(".geo", None, ".geo"))
    joined = joined.map(lambda f: f.set("names", ee.List(f.get("pa")).map(
        lambda a: ee.String(ee.Feature(a).get("NAME")).cat(" (").cat(ee.Feature(a).get("DESIG")).cat(")"))).set("pa", None))
    return {f["properties"]["id"]: f["properties"].get("names", []) for f in retry(lambda: joined.getInfo())["features"]}


def _norm(t: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()


def classify(points: pd.DataFrame, sites: list[dict]) -> dict:
    areas = protected_areas(points)
    out = {}
    for r in points.itertuples():
        ram = None
        aprox = True
        name = _norm(getattr(r, "name", "") or "")
        for s in sites:  # por nombre: el sitio "Lagos Poopo y Uru Uru" incluye a Uru Uru aunque quede lejos del punto
            key = name.replace("lago ", "").replace("laguna ", "").split(" (")[0].strip()
            if key and len(key) > 3 and key in _norm(s["name"]):
                ram, aprox = s["name"], False
                break
        for s in sites if ram is None else []:
            d = 111 * math.hypot(r.lat - s["lat"], (r.lon - s["lon"]) * math.cos(math.radians(r.lat)))
            if d <= s["radius_km"]:
                ram = s["name"]
                break
        pa = areas.get(r.id, [])
        if ram is None:  # sitios Ramsar que WDPA si trae como poligono (por ejemplo Pozuelos, en Argentina)
            ram = next((x.split(" (")[0] for x in pa if "Ramsar" in x), None)
            aprox = False
        out[r.id] = {"ramsar": ram, "ramsar_aprox": bool(ram) and aprox, "areas": pa}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    a = ap.parse_args(argv)
    ee.Initialize(project=a.project)
    sites = ramsar_sites()
    cfg = pd.read_csv(ROOT / "config" / "bodies.csv")
    main_pts = pd.DataFrame({"id": cfg.body_id, "lat": cfg.lat, "lon": cfg.lon, "name": cfg.name})
    res = classify(main_pts, sites)
    (ROOT / "data" / "real" / "protegidas.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    for k, v in res.items():
        print(f"{k:17} Ramsar: {v['ramsar'] or '-':32} areas: {', '.join(v['areas']) or '-'}")
    lakes = ROOT / "data" / "national" / "lagos.geojson"
    if lakes.exists():
        feats = json.loads(lakes.read_text(encoding="utf-8"))["features"]
        nat_pts = pd.DataFrame([{"id": f["properties"]["lake_id"], "lat": f["properties"]["lat"],
                                 "lon": f["properties"]["lon"]} for f in feats])
        nat = classify(nat_pts, sites)
        (ROOT / "data" / "national" / "protegidas.json").write_text(json.dumps(nat, ensure_ascii=False), encoding="utf-8")
        print(f"\nBarrido nacional: {sum(1 for v in nat.values() if v['ramsar'])} lagunas en sitios Ramsar, "
              f"{sum(1 for v in nat.values() if v['areas'])} en areas protegidas, de {len(nat)}")


if __name__ == "__main__":
    main()
