"""Datos hidrologicos que faltaban: evaporacion, agua consumida por cultivos y caudal del Desaguadero.

  python -m uma.hydro_extra --project TU-PROYECTO

1. Evaporacion potencial anual en la cuenca de aporte (ERA5-Land, 1985-2024) -> series.csv `pet_mm`.
   Permite que el modelo de clima use el balance lluvia - evaporacion, con sentido fisico, en lugar de
   la temperatura sola.
2. Agua consumida por cultivos en epoca seca (riego): evapotranspiracion real MODIS MOD16A2GF (NASA, 2001-2024)
   de mayo a octubre, sumada solo sobre los cultivos de MapBiomas, cerca y en la cuenca de aporte
   -> suspects.csv `crop_water_hm3` (hm3 por ano).
   Pone a prueba la hipotesis publicada para el Poopo (Satge et al. 2017): la agricultura se lleva el agua.
3. Agua en el cauce del rio Desaguadero (tramo principal entre el Titicaca y Uru Uru, HydroSHEDS) por ano
   (MapBiomas Agua) -> context `desaguadero_water_ha`, y su deficit respecto de lo esperado por el nivel del
   Titicaca y la lluvia -> sospechoso `desaguadero_deficit_idx` para Uru Uru y Poopo (senal de desvios).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import ee
import numpy as np
import pandas as pd
import statsmodels.api as sm

from uma.gee_extract import HA, MAPBIOMAS, MB_WATER, retry
from uma.suspects_upstream import basin_geometry

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "real"
YEARS = list(range(1985, 2025))
CROPS = [18, 19, 20, 21, 39, 40, 41, 62]
# lagos de pocos metros de profundidad: pierden agua sobre todo por evaporacion de su propio espejo,
# asi que importa la evaporacion sobre el lago, no el promedio de toda la cuenca
SHALLOW = ["poopo", "uru_uru", "pozuelos", "alalay", "colorada", "verde"]


def pet_series(geom) -> pd.Series:
    col = ee.ImageCollection("ECMWF/ERA5_LAND/MONTHLY_AGGR").select("potential_evaporation_sum")
    bands = [col.filterDate(f"{y}-01-01", f"{y + 1}-01-01").sum().abs().multiply(1000).rename(f"y{y}") for y in YEARS]
    v = retry(lambda: ee.Image.cat(bands).reduceRegion(ee.Reducer.mean(), geom, 11132, maxPixels=1e10,
                                                       tileScale=4).getInfo())
    return pd.Series({y: v.get(f"y{y}") for y in YEARS}, dtype=float)


def crop_water(geom, scale=500) -> pd.Series:
    """hm3 por ano evapotranspirados por cultivos: ET (mm) x area de cultivo, 2001-2024."""
    et = ee.ImageCollection("MODIS/061/MOD16A2GF").select("ET")
    mb = ee.Image(MAPBIOMAS)
    bands = []
    for y in range(2001, 2025):
        crop = mb.select(f"classification_{min(y, 2023)}").remap(CROPS, [1] * len(CROPS), 0).eq(1)
        # solo epoca seca (mayo-octubre): en esos meses un cultivo transpira si lo riegan; la evapotranspiracion
        # de todo el ano incluye la de cultivos de lluvia, que la vegetacion natural tambien gastaria
        et_mm = et.filterDate(f"{y}-01-01", f"{y + 1}-01-01").filter(ee.Filter.calendarRange(5, 10, "month")).map(
            lambda i: i.updateMask(i.lt(32761)).multiply(0.1)).sum()          # mm en la epoca seca
        vol = et_mm.divide(1000).multiply(ee.Image.pixelArea()).updateMask(crop).divide(1e6)  # hm3
        bands.append(vol.rename(f"y{y}"))
    v = retry(lambda: ee.Image.cat(bands).reduceRegion(ee.Reducer.sum(), geom, scale, maxPixels=1e11,
                                                       tileScale=8).getInfo())
    return pd.Series({y: v.get(f"y{y}") or 0.0 for y in range(2001, 2025)}, dtype=float)


def desaguadero_geometry():
    """Tramo principal del Desaguadero (HydroSHEDS) entre la salida del Titicaca y la entrada a Uru Uru."""
    rivers = ee.FeatureCollection("WWF/HydroSHEDS/v1/FreeFlowingRivers")
    box = ee.Geometry.Rectangle([-69.3, -17.85, -66.9, -16.65])
    main = rivers.filterBounds(box).filter(ee.Filter.eq("BAS_NAME", "Desaguadero")) \
        .filter(ee.Filter.gte("UPLAND_SKM", 40000))
    return main.geometry().intersection(box, 100).buffer(1000, 100)


def river_water(geom) -> pd.Series:
    img = ee.Image(MB_WATER)
    bands = [HA().updateMask(img.select(f"classification_{y}").gte(11).And(img.select(f"classification_{y}").lte(14)))
             .rename(f"y{y}") for y in YEARS]
    v = retry(lambda: ee.Image.cat(bands).reduceRegion(ee.Reducer.sum(), geom, 30, maxPixels=1e11,
                                                       tileScale=8).getInfo())
    return pd.Series({y: v.get(f"y{y}") or 0.0 for y in YEARS}, dtype=float)


def lake_pet(s: pd.DataFrame, cfg: pd.DataFrame) -> pd.DataFrame:
    """Evaporacion potencial sobre el espejo de los lagos poco profundos -> series.csv `pet_lake_mm`."""
    rows = []
    for bid in SHALLOW:
        b = cfg.loc[bid]
        p = pet_series(ee.Geometry.Point([b.lon, b.lat]).buffer(float(b.radius_km) * 1000))
        rows.append(pd.DataFrame({"body_id": bid, "year": p.index, "pet_lake_mm": p.values.round(1)}))
        print("evaporacion sobre el lago", bid, round(p.loc[:2000].mean()), "->", round(p.iloc[-5:].mean()), "mm/ano")
    s = s.drop(columns=[c for c in ("pet_lake_mm",) if c in s])
    return s.merge(pd.concat(rows), on=["body_id", "year"], how="left")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--lake-pet", action="store_true", help="solo la evaporacion sobre los lagos poco profundos")
    a = ap.parse_args(argv)
    ee.Initialize(project=a.project)
    s = pd.read_csv(DATA / "series.csv")
    if a.lake_pet:
        lake_pet(s, pd.read_csv(ROOT / "config" / "bodies.csv").set_index("body_id")).to_csv(DATA / "series.csv",
                                                                                             index=False)
        return
    sus = pd.read_csv(DATA / "suspects.csv")
    cfg = pd.read_csv(ROOT / "config" / "bodies.csv").set_index("body_id")

    # 1. evaporacion potencial
    pets = []
    for bid in s.body_id.unique():
        if (DATA / "basins" / f"{bid}.geojson").exists():
            p = pet_series(basin_geometry(bid))
            pets.append(pd.DataFrame({"body_id": bid, "year": p.index, "pet_mm": p.values.round(1)}))
            print("evaporacion", bid, round(p.mean()), "mm/ano", flush=True)
    pet = pd.concat(pets)
    s = s.drop(columns=[c for c in ("pet_mm",) if c in s]).merge(pet, on=["body_id", "year"], how="left")
    s.to_csv(DATA / "series.csv", index=False)

    # 2. agua consumida por cultivos (solo cuerpos de agua con analisis completo)
    rows = []
    targets = [b for b in ("poopo", "uru_uru", "concepcion", "titicaca_menor", "chiquitania_este", "alalay", "caceres",
                           "colorada", "verde") if b in cfg.index]
    for bid in targets:
        b = cfg.loc[bid]
        pt = ee.Geometry.Point([b.lon, b.lat])
        local = ee.FeatureCollection("WWF/HydroSHEDS/v1/Basins/hybas_8").filterBounds(pt).first().geometry() \
            .union(pt.buffer(float(b.radius_km) * 1000), 100)
        for area, geom, scale in (("subcuenca_local", local, 500), ("cuenca_aporte", basin_geometry(bid), 1000)):
            cw = crop_water(geom, scale)
            rows.append(pd.DataFrame({"body_id": bid, "year": cw.index, "suspect": "crop_water_hm3",
                                      "value": cw.values.round(2), "area": area}))
            print("cultivos", bid, area, f"{cw.iloc[0]:.1f} -> {cw.iloc[-1]:.1f} hm3", flush=True)

    # 3. Desaguadero: agua en el cauce y deficit respecto de lo esperado
    river = river_water(desaguadero_geometry())
    tit = s[s.body_id == "titicaca_menor"].set_index("year")
    rain = s[s.body_id == "uru_uru"].set_index("year")["precip_mm"]
    df = pd.DataFrame({"river": river, "titicaca": tit["water_ha"], "rain": rain}).dropna()
    base = df.loc[:2000]
    m = sm.OLS(base.river, sm.add_constant(base[["titicaca", "rain"]])).fit()
    expected = m.predict(sm.add_constant(df[["titicaca", "rain"]], has_constant="add"))
    deficit = ((expected - df.river) / base.river.mean() * 100).clip(lower=0)  # % del caudal base que no llega
    print(f"Desaguadero: agua en el cauce {river.loc[:2000].mean():.0f} ha (1985-2000) -> "
          f"{river.iloc[-5:].mean():.0f} ha (ultimos 5); modelo Titicaca+lluvia R2={m.rsquared:.2f}", flush=True)
    for bid in ("uru_uru", "poopo"):
        for area in ("subcuenca_local", "cuenca_aporte"):
            rows.append(pd.DataFrame({"body_id": bid, "year": deficit.index, "suspect": "desaguadero_deficit_idx",
                                      "value": deficit.values.round(2), "area": area}))
            rows.append(pd.DataFrame({"body_id": bid, "year": river.index, "suspect": "desaguadero_water_ha",
                                      "value": river.values.round(1), "area": area}))
    new = pd.concat(rows)
    keep = sus[~sus.suspect.isin(["crop_water_hm3", "desaguadero_deficit_idx", "desaguadero_water_ha"])]
    pd.concat([keep, new], ignore_index=True).to_csv(DATA / "suspects.csv", index=False)
    (DATA / "desaguadero.json").write_text(json.dumps({
        "r2_modelo_titicaca_lluvia": round(m.rsquared, 2), "agua_cauce_ha": {int(k): round(v) for k, v in river.items()},
        "deficit_pct": {int(k): round(v, 1) for k, v in deficit.items()}}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
