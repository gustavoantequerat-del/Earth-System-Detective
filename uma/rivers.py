"""El rio por tramos: a donde se va el agua entre el Titicaca, Uru Uru y Poopo.

  python -m uma.rivers --project TU-PROYECTO

Sigue el cauce del Desaguadero (HydroSHEDS, red de rios con su id aguas abajo) desde la salida del Titicaca y
lo corta en tramos, mas el rio Mauri (el mayor afluente, que nace en Peru). Por tramo y por ano, 1985-2024:

- agua en el cauce (MapBiomas Agua, franja de 1 km): si un tramo pierde agua que el de arriba si trae, algo
  la saca en el camino.
- verde en epoca seca (Landsat, junio-octubre, NDVI > 0.3, franja de 5 km; Landsat 8/9 ajustado a 5/7): en el Altiplano casi nada esta
  verde en la seca salvo lo que se riega y los bofedales. Si crece, crece el riego con agua del rio.
- agua artificial (MapBiomas Agua: represas, reservorios, estanques) en la misma franja.

Ademas, inventario de OpenStreetMap a lo largo del rio y alrededor de Uru Uru y Poopo: canales y acequias,
tomas y represas, minas, plantas de tratamiento y piletas de sal, con nombre y distancia al cauce.

Salidas: data/real/rio_tramos.csv, data/real/rio_tramos.geojson, data/real/rio_osm.json y, en suspects.csv,
el sospechoso `river_green_ha` (verde en seca del rio aguas arriba) para Uru Uru y Poopo.
"""
from __future__ import annotations

import argparse
import json
import math
import urllib.parse
import urllib.request
from pathlib import Path

import ee
import pandas as pd

from uma.river_reaches import FEEDS, MAURI, REACHES, RIVER_INFLOW  # noqa: F401  (RIVER_INFLOW lo usa run_engine)
from uma.gee_extract import HA, MAPBIOMAS, MB_WATER, YEARS, has_landsat, landsat_col, retry

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "real"
BOX = [-70.4, -19.3, -66.3, -16.4]
OUTLET = (-69.04, -16.57)           # salida del Titicaca (Lago Menor) al Desaguadero
GREEN_NDVI = 0.3
CROPS = [18, 19, 20, 21, 39, 40, 41, 62]


def _ends(f):
    c = f["geometry"]["coordinates"]
    c = c[0] if isinstance(c[0][0], list) else c
    return c


def network() -> tuple[dict, list[dict]]:
    """Tramos del Desaguadero y del Mauri como listas de segmentos HydroSHEDS."""
    fc = ee.FeatureCollection("WWF/HydroSHEDS/v1/FreeFlowingRivers").filterBounds(ee.Geometry.Rectangle(BOX)) \
        .filter(ee.Filter.gte("UPLAND_SKM", 800))
    feats = retry(lambda: fc.getInfo())["features"]
    by = {f["properties"]["GOID"]: f for f in feats}
    start = max((f for f in feats if math.dist(_ends(f)[0], OUTLET) < 0.15), key=lambda f: f["properties"]["UPLAND_SKM"])
    main, km, g = [], 0.0, start["properties"]["GOID"]
    while g in by and km < REACHES[-1][3]:
        f = by[g]
        main.append((km, f))
        km += f["properties"]["LENGTH_KM"]
        g = f["properties"]["NDOID"]
    main_ids = {f["properties"]["GOID"] for _, f in main}
    # Mauri: el afluente mas grande del tramo T2-T3; se sube por el segmento con mas area de aporte
    joins = [f for f in feats if f["properties"]["NDOID"] in main_ids and f["properties"]["GOID"] not in main_ids]
    mauri = [max((f for f in joins if f["properties"]["UPLAND_SKM"] < 50000), key=lambda f: f["properties"]["UPLAND_SKM"])]
    while True:
        ups = [f for f in feats if f["properties"]["NDOID"] == mauri[-1]["properties"]["GOID"]]
        if not ups or sum(f["properties"]["LENGTH_KM"] for f in mauri) > 160:
            break
        mauri.append(max(ups, key=lambda f: f["properties"]["UPLAND_SKM"]))
    reaches = {}
    for rid, name, a, b in REACHES:
        segs = [f for k, f in main if a <= k < b]
        reaches[rid] = {"name": name, "km": [a, b], "segments": segs}
    reaches[MAURI[0]] = {"name": MAURI[1], "km": None, "segments": mauri}
    return reaches, feats


def _mouth(rid: str, r: dict) -> dict:
    """Segmento de aguas abajo del tramo (el Mauri se recorrio hacia arriba: su boca es el primero)."""
    return (r["segments"][0] if rid == MAURI[0] else r["segments"][-1])["properties"]


def write_geojson(reaches: dict) -> None:
    gj = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "MultiLineString", "coordinates": [_ends(f) for f in r["segments"]]},
         "properties": {"reach": rid, "name": r["name"], "km": r["km"],
                        "uso_consuntivo_pct": round(_mouth(rid, r)["USE"], 1),
                        "regulacion_pct": round(_mouth(rid, r)["DOR"], 1)}}
        for rid, r in reaches.items()]}
    (DATA / "rio_tramos.geojson").write_text(json.dumps(gj), encoding="utf-8")


def _line(segs) -> ee.Geometry:
    return ee.Geometry.MultiLineString([_ends(f) for f in segs])


def yearly(reaches: dict, only: set | None = None) -> pd.DataFrame:
    fc = ee.FeatureCollection([
        ee.Feature(_line(r["segments"]).buffer(1000, 200), {"reach": rid, "band": "cauce"}) for rid, r in reaches.items()
    ] + [
        ee.Feature(_line(r["segments"]).buffer(5000, 500), {"reach": rid, "band": "franja"}) for rid, r in reaches.items()
    ])
    region = fc.geometry().bounds()
    mbw, mb = ee.Image(MB_WATER), ee.Image(MAPBIOMAS)
    rows = []
    for y in YEARS:
        w = mbw.select(f"classification_{y}").unmask(0)  # fuera del agua la capa viene vacia
        natural = w.gte(11).And(w.lte(14))
        artificial = w.gte(21).And(w.lte(23))
        crop = mb.select(f"classification_{min(y, 2023)}").remap(CROPS, [1] * len(CROPS), 0).eq(1)
        bands = [HA().updateMask(natural).rename("water_ha"), HA().updateMask(artificial).rename("artificial_ha"),
                 HA().updateMask(crop).rename("crop_ha")]
        if has_landsat(y, region):
            ls = landsat_col(y, region, harmonize=True).median()  # Landsat 8/9 llevado a la escala de 5/7
            ndvi = ls.normalizedDifference(["NIR", "R"])
            mndwi = ls.normalizedDifference(["G", "SWIR1"])
            bands.append(HA().updateMask(ndvi.gt(GREEN_NDVI).And(mndwi.lt(0)).And(natural.Not())).rename("green_ha"))
        img = ee.Image.cat(bands).unmask(0)
        res = retry(lambda: img.reduceRegions(fc, ee.Reducer.sum(), 30, tileScale=8).getInfo())
        for f in res["features"]:
            p = f["properties"]
            keys = ["water_ha"] if p["band"] == "cauce" else ["artificial_ha", "crop_ha", "green_ha"]
            for k in keys:
                if k in p and (only is None or k in only):
                    rows.append({"reach": p["reach"], "year": y, "var": k, "value": round(p[k], 1)})
        print(y, "ok", flush=True)
    return pd.DataFrame(rows)


OSM_TAGS = [("Canal o acequia", 'way["waterway"~"canal|ditch|drain"]'),
            ("Represa o toma", 'nwr["waterway"~"dam|weir"]'), ("Represa o toma", 'nwr["man_made"="dam"]'),
            ("Reservorio", 'nwr["landuse"="reservoir"]'), ("Reservorio", 'nwr["water"="reservoir"]'),
            ("Mina o cantera", 'nwr["landuse"="quarry"]'), ("Mina o cantera", 'nwr["industrial"="mine"]'),
            ("Mina o cantera", 'nwr["man_made"~"mineshaft|adit"]'),
            ("Planta de tratamiento", 'nwr["man_made"="wastewater_plant"]'), ("Piletas de sal", 'nwr["landuse"="salt_pond"]')]


def osm_inventory(reaches: dict) -> list[dict]:
    bbox = "-19.3,-69.8,-16.5,-66.5"
    q = "[out:json][timeout:120];(" + "".join(f"{t}({bbox});" for _, t in OSM_TAGS) + ");out center tags;"
    req = urllib.request.Request("https://overpass-api.de/api/interpreter",
                                 data=urllib.parse.urlencode({"data": q}).encode(),
                                 headers={"User-Agent": "detector-huella-humana/1.0"})
    with urllib.request.urlopen(req, timeout=180) as r:
        els = json.load(r)["elements"]
    pts = [(rid, c) for rid, r in reaches.items() for f in r["segments"] for c in _ends(f)]
    out = []
    for e in els:
        tags = e.get("tags", {})
        lat, lon = (e["lat"], e["lon"]) if "lat" in e else (e["center"]["lat"], e["center"]["lon"])
        kind = next((k for k, t in OSM_TAGS if _match(t, tags)), "Otro")
        rid, d = min(((rid, 111 * math.hypot(lat - c[1], (lon - c[0]) * math.cos(math.radians(lat)))) for rid, c in pts),
                     key=lambda x: x[1])
        lakes = {b: 111 * math.hypot(lat - la, (lon - lo) * math.cos(math.radians(lat)))
                 for b, (la, lo) in {"uru_uru": (-18.07, -67.12), "poopo": (-18.85, -67.05)}.items()}
        near_lake = min(lakes, key=lakes.get)
        if d > 15 and lakes[near_lake] > 45:
            continue
        out.append({"kind": kind, "name": tags.get("name", ""), "lat": round(lat, 4), "lon": round(lon, 4),
                    "reach": rid if d <= 15 else None, "dist_rio_km": round(d, 1),
                    "lake": near_lake if lakes[near_lake] <= 45 else None, "dist_lago_km": round(lakes[near_lake], 1),
                    "osm": f"https://www.openstreetmap.org/{e['type']}/{e['id']}"})
    return out


def _match(t: str, tags: dict) -> bool:
    import re
    k, v = re.search(r'\["([^"]+)"[~=]"([^"]+)"\]', t).groups()
    return k in tags and re.fullmatch(v, tags[k]) is not None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--skip-osm", action="store_true")
    ap.add_argument("--only-map", action="store_true", help="solo rehacer rio_tramos.geojson")
    ap.add_argument("--only-green", action="store_true", help="solo rehacer el verde en epoca seca")
    a = ap.parse_args(argv)
    ee.Initialize(project=a.project)
    reaches, _ = network()
    for rid, r in reaches.items():
        p = _mouth(rid, r)
        print(rid, r["name"], len(r["segments"]), f"segmentos; uso consuntivo {p['USE']:.1f}%, regulacion {p['DOR']:.1f}%")
    write_geojson(reaches)
    if a.only_map:
        return
    if a.only_green:  # rehacer solo el verde en epoca seca
        old = pd.read_csv(DATA / "rio_tramos.csv")
        df = pd.concat([old[old["var"] != "green_ha"], yearly(reaches, {"green_ha"})], ignore_index=True)
    else:
        df = yearly(reaches)
    df.to_csv(DATA / "rio_tramos.csv", index=False)

    green = df[df["var"] == "green_ha"].pivot(index="year", columns="reach", values="value")
    green = green.reindex(YEARS).interpolate(limit_direction="both")
    sus = pd.read_csv(DATA / "suspects.csv")
    sus = sus[sus.suspect != "river_green_ha"]
    new = []
    for bid, rids in FEEDS.items():
        v = green[[r for r in rids if r in green]].sum(axis=1)
        new.append(pd.DataFrame({"body_id": bid, "year": v.index, "suspect": "river_green_ha",
                                 "value": v.values.round(1), "area": "rio"}))
    pd.concat([sus, *new], ignore_index=True).to_csv(DATA / "suspects.csv", index=False)

    if not a.skip_osm:
        inv = osm_inventory(reaches)
        (DATA / "rio_osm.json").write_text(json.dumps(inv, ensure_ascii=False, indent=1), encoding="utf-8")
        print(pd.Series([x["kind"] for x in inv]).value_counts().to_string())


if __name__ == "__main__":
    main()
