"""Clima de NASA POWER para cada cuerpo de agua, sin cuenta ni clave.

  python -m uma.nasa_power            # todos los cuerpos de agua de config/bodies.csv

NASA POWER (power.larc.nasa.gov) entrega lluvia corregida (PRECTOTCORR, basada en MERRA-2 e IMERG)
y temperatura a 2 m (T2M, MERRA-2) mensuales desde 1981, en una grilla de 0.5 x 0.625 grados.
Guarda data/real/nasa_power.csv (anual) y data/real/nasa_power_monthly.csv, y tambien el ONI de NOAA.
"""
from __future__ import annotations

import calendar
import math
import io
import json
import time
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
URL = ("https://power.larc.nasa.gov/api/temporal/monthly/point?parameters=PRECTOTCORR,T2M"
       "&community=AG&longitude={lon}&latitude={lat}&start={start}&end={end}&format=JSON")
ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"


def fetch(lat, lon, start=1985, end=2024):
    for i in range(3):
        try:
            with urllib.request.urlopen(URL.format(lat=lat, lon=lon, start=start, end=end), timeout=120) as r:
                return json.load(r)["properties"]["parameter"]
        except Exception as e:
            if i == 2:
                raise
            print("  reintento:", e)
            time.sleep(5)


def _in_ring(x, y, ring):
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _polys(g):
    """Lista de poligonos (anillos) de un Polygon, MultiPolygon o GeometryCollection."""
    if g["type"] == "Polygon":
        return [g["coordinates"]]
    if g["type"] == "MultiPolygon":
        return g["coordinates"]
    if g["type"] == "GeometryCollection":
        return [p for sub in g["geometries"] for p in _polys(sub)]
    return []


def _in_geom(x, y, g):
    polys = _polys(g)
    return any(_in_ring(x, y, p[0]) and not any(_in_ring(x, y, h) for h in p[1:]) for p in polys)


def basin_points(body_id, lat, lon, step=1.0):
    """Puntos de una grilla de `step` grados dentro de la cuenca de aporte (si existe), mas el propio lago."""
    f = ROOT / "data" / "real" / "basins" / f"{body_id}.geojson"
    pts = [(round(lat, 2), round(lon, 2))]
    if not f.exists():
        return pts
    g = json.loads(f.read_text(encoding="utf-8"))["geometry"]
    coords = [c for poly in _polys(g) for c in poly[0]]
    xs, ys = [c[0] for c in coords], [c[1] for c in coords]
    y = math.floor(min(ys)) + step / 2
    while y < max(ys):
        x = math.floor(min(xs)) + step / 2
        while x < max(xs):
            if _in_geom(x, y, g):
                pts.append((round(y, 2), round(x, 2)))
            x += step
        y += step
    return pts


_cache: dict = {}


def point_monthly(lat, lon):
    if (lat, lon) not in _cache:
        p = fetch(lat, lon)
        rows = []
        for key, mm_day in p["PRECTOTCORR"].items():
            y, m = int(key[:4]), int(key[4:])
            if m == 13 or mm_day == -999:  # 13 = promedio anual que trae la API; -999 = sin dato
                continue
            t = p["T2M"].get(key, -999)
            rows.append({"year": y, "month": m, "precip_mm": mm_day * calendar.monthrange(y, m)[1],
                         "temp_c": None if t == -999 else t})
        _cache[(lat, lon)] = pd.DataFrame(rows)
    return _cache[(lat, lon)]


def main():
    out = ROOT / "data" / "real"
    out.mkdir(parents=True, exist_ok=True)
    cfg = pd.read_csv(ROOT / "config" / "bodies.csv")
    monthly = []
    for _, b in cfg.iterrows():
        pts = basin_points(b.body_id, b.lat, b.lon)
        print(f"NASA POWER: {b['name']} ({len(pts)} puntos de la cuenca de aporte)")
        m = pd.concat([point_monthly(*p) for p in pts]).groupby(["year", "month"]).mean().reset_index()
        m.insert(0, "body_id", b.body_id)
        m["n_points"] = len(pts)
        monthly.append(m)
    mdf = pd.concat(monthly)
    mdf.to_csv(out / "nasa_power_monthly.csv", index=False)
    full = mdf.groupby(["body_id", "year"]).filter(
        lambda g: len(g) == 12 and g.month.nunique() == 12
        and g[["precip_mm", "temp_c"]].notna().all().all())  # doce meses válidos, no solo doce filas
    annual = full.groupby(["body_id", "year"]).agg(precip_mm=("precip_mm", "sum"), temp_c=("temp_c", "mean")).reset_index()
    annual.round(2).to_csv(out / "nasa_power.csv", index=False)
    print(f"  {len(annual)} filas anuales -> {out / 'nasa_power.csv'}")

    with urllib.request.urlopen(ONI_URL, timeout=60) as r:
        oni = pd.read_csv(io.StringIO(r.read().decode()), sep=r"\s+")
    oni.to_csv(out / "oni_trimestral.csv", index=False)
    oni.groupby("YR")["ANOM"].mean().rename("oni").reset_index().rename(columns={"YR": "year"}) \
        .round(3).to_csv(out / "oni.csv", index=False)
    print(f"ONI de NOAA -> {out / 'oni.csv'}")


if __name__ == "__main__":
    main()
