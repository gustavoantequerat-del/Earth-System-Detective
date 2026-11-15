"""Series mensuales: 12 veces mas datos que las anuales para el modelo de clima y las pruebas.

  python -m uma.monthly --project TU-PROYECTO

- agua por mes: JRC Global Surface Water MonthlyHistory (Landsat, 1985-2021) en la misma area que la serie anual.
  Un mes con mas del 10% del area sin observar (nubes, huecos) queda vacio: no se rellena.
- lluvia por mes: promedio de NASA POWER (ya descargada, nasa_power_monthly.csv) y CHIRPS, en la cuenca de aporte.
- evaporacion potencial por mes: ERA5-Land en la cuenca y, en los lagos poco profundos, sobre el propio lago.
- El Nino por mes: ONI trimestral centrado en el mes (NOAA).
- agua por mes en el Desaguadero antes de Uru Uru (tramo T4), para usar como entrada aguas arriba.

Salida: data/real/monthly.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path

import ee
import pandas as pd

from uma.gee_extract import HA, retry
from uma.hydro_extra import SHALLOW
from uma.suspects_upstream import basin_geometry

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "real"
YEARS = list(range(1985, 2025))
JRC_LAST = 2021
NODATA_MAX = 10.0
SEASONS = {"DJF": 1, "JFM": 2, "FMA": 3, "MAM": 4, "AMJ": 5, "MJJ": 6, "JJA": 7, "JAS": 8, "ASO": 9, "SON": 10,
           "OND": 11, "NDJ": 12}


def water_monthly(area) -> pd.DataFrame:
    col = ee.ImageCollection("JRC/GSW1_4/MonthlyHistory")
    rows = []
    for y in range(1985, JRC_LAST + 1):
        imgs = col.filter(ee.Filter.calendarRange(y, y, "year"))
        bands = []
        for m in range(1, 13):
            w = imgs.filter(ee.Filter.calendarRange(m, m, "month")).first()
            w = ee.Image(ee.Algorithms.If(w, ee.Image(w).select("water"), ee.Image.constant(0).rename("water")))
            bands += [HA().updateMask(w.eq(2)).rename(f"w{m}"), HA().updateMask(w.eq(0)).rename(f"n{m}")]
        img = ee.Image.cat(bands + [HA().rename("total")])
        v = retry(lambda: img.reduceRegion(ee.Reducer.sum(), area, 30, maxPixels=1e11, tileScale=8).getInfo())
        total = v.get("total") or 1
        for m in range(1, 13):
            nod = 100 * (v.get(f"n{m}") or 0) / total
            rows.append({"year": y, "month": m, "nodata_pct": round(nod, 1),
                         "water_ha": round(v.get(f"w{m}") or 0.0, 1) if nod <= NODATA_MAX else None})
        print("  ", y, "ok", flush=True)
    return pd.DataFrame(rows)


def _monthly_stack(fn, scale: int, geom) -> pd.DataFrame:
    rows = []
    for y0 in range(1985, 2025, 10):  # por decada, para no pasar el limite de bandas
        bands = []
        for y in range(y0, min(y0 + 10, 2025)):
            for m in range(1, 13):
                start = ee.Date.fromYMD(y, m, 1)
                bands.append(fn(start, start.advance(1, "month")).rename(f"y{y}m{m}"))
        v = retry(lambda: ee.Image.cat(bands).reduceRegion(ee.Reducer.mean(), geom, scale, maxPixels=1e11,
                                                           tileScale=4).getInfo())
        for k, val in v.items():
            y, m = k[1:].split("m")
            rows.append({"year": int(y), "month": int(m), "value": val})
    return pd.DataFrame(rows)


def chirps(geom) -> pd.DataFrame:
    col = ee.ImageCollection("UCSB-CHG/CHIRPS/PENTAD").select("precipitation")
    return _monthly_stack(lambda a, b: col.filterDate(a, b).sum(), 5566, geom).rename(columns={"value": "precip_chirps_mm"})


def pet(geom) -> pd.DataFrame:
    col = ee.ImageCollection("ECMWF/ERA5_LAND/MONTHLY_AGGR").select("potential_evaporation_sum")
    return _monthly_stack(lambda a, b: col.filterDate(a, b).first().abs().multiply(1000), 11132, geom) \
        .rename(columns={"value": "pet_mm"})


def oni_monthly() -> pd.DataFrame:
    o = pd.read_csv(DATA / "oni_trimestral.csv")
    o["month"] = o.SEAS.map(SEASONS)
    return o.rename(columns={"YR": "year", "ANOM": "oni"})[["year", "month", "oni"]]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--only", default="")
    a = ap.parse_args(argv)
    ee.Initialize(project=a.project)
    cfg = pd.read_csv(ROOT / "config" / "bodies.csv")
    if a.only:
        cfg = cfg[cfg.body_id.isin(a.only.split(","))]
    power = pd.read_csv(DATA / "nasa_power_monthly.csv")[["body_id", "year", "month", "precip_mm"]] \
        .rename(columns={"precip_mm": "precip_power_mm"})
    oni = oni_monthly()
    out = []
    for b in cfg.itertuples():
        print("==", b.body_id, flush=True)
        pt = ee.Geometry.Point([b.lon, b.lat])
        area = pt.buffer(float(b.radius_km) * 1000)
        basin = basin_geometry(b.body_id) if (DATA / "basins" / f"{b.body_id}.geojson").exists() else area
        df = pd.DataFrame([{"year": y, "month": m} for y in YEARS for m in range(1, 13)])
        df = df.merge(water_monthly(area), on=["year", "month"], how="left")
        df = df.merge(chirps(basin), on=["year", "month"], how="left").merge(pet(basin), on=["year", "month"], how="left")
        if b.body_id in SHALLOW:
            df = df.merge(pet(area).rename(columns={"pet_mm": "pet_lake_mm"}), on=["year", "month"], how="left")
        df["body_id"] = b.body_id
        out.append(df)
    if not a.only or "uru_uru" in a.only:
        from uma import rivers
        reaches, _ = rivers.network()
        geom = rivers._line(reaches["T4"]["segments"]).buffer(1000, 200)
        print("== rio T4 (entrada a Uru Uru)", flush=True)
        r = water_monthly(geom).rename(columns={"water_ha": "river_t4_ha", "nodata_pct": "river_t4_nodata"})
        out = [d.merge(r, on=["year", "month"], how="left") if d.body_id.iloc[0] == "uru_uru" else d for d in out]
    res = pd.concat(out, ignore_index=True)
    res = res.merge(power, on=["body_id", "year", "month"], how="left").merge(oni, on=["year", "month"], how="left")
    res["precip_mm"] = res[["precip_power_mm", "precip_chirps_mm"]].mean(axis=1)
    f = DATA / "monthly.csv"
    if a.only and f.exists():
        old = pd.read_csv(f)
        res = pd.concat([old[~old.body_id.isin(res.body_id.unique())], res], ignore_index=True)
    res.to_csv(f, index=False)
    print("listo:", len(res), "filas;", res.groupby("body_id").water_ha.count().to_dict())


if __name__ == "__main__":
    main()
