"""Extrae de Google Earth Engine todo lo que necesita Uma y lo guarda en data/real/.

  python -m uma.gee_extract --project TU-PROYECTO
  python -m uma.gee_extract --project TU-PROYECTO --only poopo,coipasa   # algunos cuerpos de agua
  python -m uma.gee_extract --project TU-PROYECTO --skip-images          # solo series

Salida en data/real/:
  bodies.csv, series.csv, suspects.csv   entrada del motor (ver README)
  check.csv                              verificacion: superficie maxima de agua de JRC en cada area
  img/<body>_<year>.png                  Landsat epoca seca, color verdadero (antes y despues)
  img/<body>_<year>_water.png            mascara de agua JRC de ese ano
  oni.csv                                El Nino / La Nina de NOAA
  nasa_power.csv                         lluvia y temperatura NASA POWER (si no existe, se baja)

Fuentes por defecto, todas de NASA salvo el ONI (NOAA):
  agua       Landsat 5/7/8/9 (NASA/USGS), indice MNDWI en epoca seca, 1985-2024
             (JRC Global Surface Water se guarda en water_ha_jrc solo para validar, llega a 2021)
  clima      NASA POWER (lluvia PRECTOTCORR, temperatura T2M de MERRA-2)  [--climate chirps: CHIRPS + ERA5]
  sospechosos  MODIS MCD64A1 (fuego), Landsat (riego), Hansen (desmonte, derivado de Landsat), GHSL (ciudad)

Antes: `earthengine authenticate` una vez, y un proyecto de Google Cloud registrado en Earth Engine.
Los IDs de los datasets cambian de version: si algo falla, verificar en el catalogo de Earth Engine.
"""
from __future__ import annotations

import argparse
import io
import sys
import time
import urllib.request
from pathlib import Path

import ee
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
YEARS = list(range(1985, 2025))
JRC_LAST = 2021                          # JRC YearlyHistory: 1984-2021
IMG_YEARS = [1990, 2000, 2010, 2016, 2021, 2024]
ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"

DS = {
    "jrc_yearly": "JRC/GSW1_4/YearlyHistory",
    "jrc": "JRC/GSW1_4/GlobalSurfaceWater",
    "chirps": "UCSB-CHG/CHIRPS/DAILY",
    "era5": "ECMWF/ERA5_LAND/MONTHLY_AGGR",
    "basins": "WWF/HydroSHEDS/v1/Basins/hybas_8",
    "hansen": "UMD/hansen/global_forest_change_2025_v1_13",
    "burned": "MODIS/061/MCD64A1",
    "ghsl": "JRC/GHSL/P2023A/GHS_BUILT_S",
    "dmsp": "NOAA/DMSP-OLS/NIGHTTIME_LIGHTS",
    "viirs": "NOAA/VIIRS/DNB/ANNUAL_V22",
    "viirs21": "NOAA/VIIRS/DNB/ANNUAL_V21",
    "worldpop": "WorldPop/GP/100m/pop",
    "grace": "NASA/GRACE/MASS_GRIDS_V04/MASCON",
    "l5": "LANDSAT/LT05/C02/T1_L2",
    "l7": "LANDSAT/LE07/C02/T1_L2",
    "l8": "LANDSAT/LC08/C02/T1_L2",
    "l9": "LANDSAT/LC09/C02/T1_L2",
}


SCALE_MULT = 1  # se sube para cuencas muy grandes (resolucion mas gruesa, mismo resultado en hectareas)


def S(base_m):
    """Escala de calculo en metros, ajustada al tamano del area."""
    return base_m * SCALE_MULT


def log(*a):
    print(*a, flush=True)


def retry(fn, tries=6):
    """Reintenta ante limites de cuota de Earth Engine (429, 'Too many concurrent aggregations')."""
    for i in range(tries):
        try:
            return fn()
        except ee.EEException as e:
            msg = str(e).lower()
            transient = any(k in msg for k in ("too many", "quota", "rate", "timed out", "timeout", "internal", "unavailable"))
            if i == tries - 1 or not transient:
                raise
            wait = min(60, 10 * (i + 1))
            log(f"   reintento en {wait}s ({str(e)[:80]})")
            time.sleep(wait)
        except (ConnectionError, OSError) as e:  # corte de internet: esperar mas
            if i == tries - 1:
                raise
            log(f"   sin conexion, reintento en 60s ({str(e)[:60]})")
            time.sleep(60)


# ------------------------------------------------------------------ geometria
def HA():
    return ee.Image.pixelArea().divide(1e4)


def basin_for(pt):
    """Subcuenca HydroBASINS nivel 8 que contiene el punto, unida al area del cuerpo de agua.

    Es la subcuenca local, no toda el area aguas arriba: suficiente para el MVP.
    """
    b = ee.FeatureCollection(DS["basins"]).filterBounds(pt).first().geometry()
    return b


# ------------------------------------------------------------------ Landsat
def _prep_landsat(img, rgb_bands, nir, swir):
    qa = img.select("QA_PIXEL")
    clear = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))
    sr = img.select([*rgb_bands, nir, swir], ["R", "G", "B", "NIR", "SWIR1"]).multiply(0.0000275).add(-0.2)
    return sr.updateMask(clear)


def landsat_dry(year, region):
    """Mediana de epoca seca (junio-octubre) con el Landsat disponible ese ano."""
    return landsat_col(year, region).median()


def has_landsat(year, region) -> bool:
    return retry(lambda: landsat_col(year, region).size().getInfo()) > 0


def landsat_col(year, region):
    start, end = f"{year}-06-01", f"{year}-10-31"
    parts = []
    if year <= 2012:
        parts.append(ee.ImageCollection(DS["l5"]).filterDate(start, end).filterBounds(region)
                     .map(lambda i: _prep_landsat(i, ["SR_B3", "SR_B2", "SR_B1"], "SR_B4", "SR_B5")))
    if 2011 <= year <= 2013:
        parts.append(ee.ImageCollection(DS["l7"]).filterDate(start, end).filterBounds(region)
                     .map(lambda i: _prep_landsat(i, ["SR_B3", "SR_B2", "SR_B1"], "SR_B4", "SR_B5")))
    if year >= 2013:
        for k in ("l8", "l9"):
            parts.append(ee.ImageCollection(DS[k]).filterDate(start, end).filterBounds(region)
                         .map(lambda i: _prep_landsat(i, ["SR_B4", "SR_B3", "SR_B2"], "SR_B5", "SR_B6")))
    col = parts[0]
    for p in parts[1:]:
        col = col.merge(p)
    return col


def landsat_vis(img):
    return img.select(["R", "G", "B"]).visualize(min=0, max=0.25, gamma=1.3)


# ------------------------------------------------------------------ series
def water_series(area):
    yearly = ee.ImageCollection(DS["jrc_yearly"])

    rows = []
    for y in [y for y in YEARS if y <= JRC_LAST]:  # un ano por pedido: la cuota no admite muchos en paralelo
        wc = yearly.filter(ee.Filter.eq("year", y)).first().select("waterClass")
        stack = HA().updateMask(wc.gte(2)).rename("water").addBands(HA().updateMask(wc.eq(0)).rename("nodata")) \
            .addBands(HA().rename("total"))
        v = retry(lambda: stack.reduceRegion(ee.Reducer.sum(), area, 30, maxPixels=1e11, tileScale=4).getInfo())
        total = v.get("total") or 1
        rows.append({"year": y, "water_ha": v.get("water") or 0.0,
                     "nodata_pct": 100 * (v.get("nodata") or 0) / total})
    return pd.DataFrame(rows)


def water_landsat(area):
    """Agua de epoca seca con Landsat (NASA/USGS): pixeles con MNDWI > 0 en la mediana jun-oct.

    Llega hasta el ultimo ano de Landsat 9, a diferencia de JRC.
    """
    rows = []
    for y in YEARS:
        if not has_landsat(y, area):
            log(f"   {y}: sin imagenes Landsat en epoca seca, se interpola")
            rows.append({"year": y, "water_ha": None, "nodata_pct": 100.0})
            continue
        img = landsat_dry(y, area)
        mndwi = img.normalizedDifference(["G", "SWIR1"])
        stack = (HA().updateMask(mndwi.gt(0)).rename("water")
                 .addBands(HA().updateMask(mndwi.mask()).rename("valid")).addBands(HA().rename("total")))
        v = retry(lambda: stack.reduceRegion(ee.Reducer.sum(), area, 30, maxPixels=1e11, tileScale=4).getInfo())
        total = v.get("total") or 1
        rows.append({"year": y, "water_ha": v.get("water") or 0.0,
                     "nodata_pct": 100 * (1 - (v.get("valid") or 0) / total)})
    return pd.DataFrame(rows)


def climate_series(basin):
    chirps, era5 = ee.ImageCollection(DS["chirps"]), ee.ImageCollection(DS["era5"])

    def per_year(y):
        y = ee.Number(y)
        start, end = ee.Date.fromYMD(y, 1, 1), ee.Date.fromYMD(y.add(1), 1, 1)
        p = chirps.filterDate(start, end).sum().reduceRegion(ee.Reducer.mean(), basin, 5566, maxPixels=1e10)
        t = era5.filterDate(start, end).select("temperature_2m").mean() \
            .reduceRegion(ee.Reducer.mean(), basin, 11132, maxPixels=1e10)
        return ee.Feature(None, {"year": y, "precip_mm": p.get("precipitation"),
                                 "temp_c": ee.Number(t.get("temperature_2m")).subtract(273.15)})
    fc = ee.FeatureCollection(ee.List(YEARS).map(per_year))
    return pd.DataFrame([f["properties"] for f in retry(fc.getInfo)["features"]])


def forest_loss(basin):
    g = retry(lambda: HA().addBands(ee.Image(DS["hansen"]).select("lossyear"))
              .reduceRegion(ee.Reducer.sum().group(groupField=1, groupName="ly"), basin, S(100),
                            maxPixels=1e11, tileScale=4).get("groups").getInfo())
    return pd.DataFrame([{"year": 2000 + x["ly"], "value": x["sum"]} for x in g if x["ly"] > 0],
                        columns=["year", "value"])


def burned(basin):
    col = ee.ImageCollection(DS["burned"])

    rows = []
    for y in [y for y in YEARS if y >= 2001]:
        img = col.filter(ee.Filter.calendarRange(y, y, "year")).select("BurnDate").max()
        v = retry(lambda: HA().updateMask(img.gt(0)).reduceRegion(ee.Reducer.sum(), basin, 500, maxPixels=1e10)
                  .get("area").getInfo())
        rows.append({"year": y, "value": v or 0.0})
    return pd.DataFrame(rows)


def dry_crops(basin):
    """Vegetacion verde en plena epoca seca fuera del bosque original: senal de riego."""
    nonforest = ee.Image(DS["hansen"]).select("treecover2000").lt(30)
    rows = []
    for y in YEARS:
        if not has_landsat(y, basin):
            rows.append({"year": y, "value": None})
            continue
        img = landsat_dry(y, basin)
        ndvi = img.normalizedDifference(["NIR", "R"])
        v = retry(lambda: HA().updateMask(ndvi.gt(0.45).And(nonforest))
                  .reduceRegion(ee.Reducer.sum(), basin, S(120), maxPixels=1e11, tileScale=4).get("area").getInfo())
        rows.append({"year": y, "value": v or 0.0})
    df = pd.DataFrame(rows)
    missing = df["value"].isna()
    df["value"] = df["value"].astype(float).interpolate(limit_area="inside")
    df["value_status"] = "observed"
    df.loc[missing & df.value.notna(), "value_status"] = "interpolated"
    df.loc[df.value.isna(), "value_status"] = "unavailable"
    return df


def urban(basin):
    """Superficie construida GHSL (epocas cada 5 anos), interpolada por ano."""
    col = ee.ImageCollection(DS["ghsl"])
    epochs = list(range(1975, 2025, 5))
    rows = []
    for e in epochs:
        img = col.filter(ee.Filter.eq("system:index", str(e))).first().select("built_surface")
        v = retry(lambda: img.divide(1e4).reduceRegion(ee.Reducer.sum(), basin, S(100), maxPixels=1e11, tileScale=4)
                  .get("built_surface").getInfo())
        rows.append({"year": e, "value": v or 0.0})
    s = pd.DataFrame(rows).set_index("year")["value"].reindex(range(1975, 2025)).interpolate()
    return s.loc[YEARS[0]:YEARS[-1]].reset_index()


MAPBIOMAS = "projects/mapbiomas-public/assets/bolivia/collection2/mapbiomas_bolivia_collection2_integration_v1"
# leyenda MapBiomas: 30 mineria, 24 infraestructura urbana, 15 pasto, 18/19/20/39/40/41/62 agricultura
MB_CLASSES = {"mining_ha": [30], "urban_ha": [24], "pasture_ha": [15], "agri_ha": [18, 19, 20, 39, 40, 41, 62]}
_mb_cache: dict = {}


def mapbiomas(basin, key):
    """Hectareas por ano de cada clase de MapBiomas Bolivia (1985-2023) en la cuenca.

    Se calcula una sola vez por cuenca para las cuatro clases y se guarda en cache.
    """
    ck = id(basin)
    if ck not in _mb_cache:
        img = ee.Image(MAPBIOMAS)
        codes = sum(MB_CLASSES.values(), [])
        groups = sum(([i] * len(v) for i, v in enumerate(MB_CLASSES.values())), [])
        rows = []
        for y in range(1985, 2024):
            cls = img.select(f"classification_{y}").remap(codes, groups, -1)
            g = retry(lambda: HA().addBands(cls).updateMask(cls.gte(0))
                      .reduceRegion(ee.Reducer.sum().group(1, "k"), basin, S(30), maxPixels=1e11, tileScale=4)
                      .get("groups").getInfo())
            row = {"year": y, **{k: 0.0 for k in MB_CLASSES}}
            for x in g:
                row[list(MB_CLASSES)[x["k"]]] = x["sum"]
            rows.append(row)
        _mb_cache.clear()
        _mb_cache[ck] = pd.DataFrame(rows)
    return _mb_cache[ck][["year", key]].rename(columns={key: "value"})


def night_lights(basin):
    """Luz nocturna en la cuenca: DMSP-OLS 1992-2013 y VIIRS 2014 en adelante, empalmados en 2013.

    Senal de ciudad e industria. Los dos sensores no son comparables directamente, por eso VIIRS
    se escala con el cociente de ambos en 2013.
    """
    dmsp = ee.ImageCollection(DS["dmsp"])
    # VIIRS anual: V21 cubre 2012-2021 y V22 desde 2022
    viirs = ee.ImageCollection(DS["viirs21"]).merge(
        ee.ImageCollection(DS["viirs"]).filter(ee.Filter.calendarRange(2022, 2100, "year")))

    def total(img, band, scale):
        return retry(lambda: img.select(band).reduceRegion(ee.Reducer.sum(), basin, scale, maxPixels=1e11)
                     .get(band).getInfo()) or 0.0
    d_rows, v_rows = {}, {}
    for y in range(1992, 2014):
        imgs = dmsp.filter(ee.Filter.calendarRange(y, y, "year"))
        if retry(lambda: imgs.size().getInfo()):
            d_rows[y] = total(imgs.mean(), "stable_lights", 1000)
    for y in range(2012, YEARS[-1] + 1):
        imgs = viirs.filter(ee.Filter.calendarRange(y, y, "year"))
        if retry(lambda: imgs.size().getInfo()):
            v_rows[y] = total(imgs.first(), "average_masked", 500)
    common = sorted(set(d_rows) & set(v_rows))
    ratio = d_rows[common[-1]] / v_rows[common[-1]] if common and v_rows[common[-1]] else 1.0
    last_d = max(d_rows) if d_rows else 0
    rows = {**d_rows, **{y: v * ratio for y, v in v_rows.items() if y > last_d}}
    return pd.DataFrame({"year": list(rows), "value": list(rows.values())})


def population(basin):
    """Poblacion en la cuenca (WorldPop, 2000-2020)."""
    col = ee.ImageCollection(DS["worldpop"]).filter(ee.Filter.eq("country", "BOL"))
    rows = []
    for y in range(2000, 2021):
        img = col.filter(ee.Filter.eq("year", y)).mosaic()
        v = retry(lambda: img.reduceRegion(ee.Reducer.sum(), basin, 100, maxPixels=1e11, tileScale=4)  # conteo de personas: siempre a 100 m
                  .get("population").getInfo())
        rows.append({"year": y, "value": v or 0.0})
    return pd.DataFrame(rows)


def groundwater(basin):
    """Agua total almacenada en la cuenca (GRACE/GRACE-FO, NASA): anomalia anual en cm de agua.

    No es un sospechoso: indica si tambien baja el agua del subsuelo (bombeo o sequia).
    """
    col = ee.ImageCollection(DS["grace"]).select("lwe_thickness")
    rows = []
    for y in range(2002, 2025):
        imgs = col.filter(ee.Filter.calendarRange(y, y, "year"))
        v = retry(lambda: imgs.mean().reduceRegion(ee.Reducer.mean(), basin.centroid(1000).buffer(30000), 5000)
                  .get("lwe_thickness").getInfo())
        rows.append({"year": y, "groundwater_cm": v})
    return pd.DataFrame(rows)


MB_WATER = "projects/mapbiomas-public/assets/bolivia/water/collection4/mapbiomas_bolivia_collection4_water_bodies_v1"
# tipos de cuerpo de agua de MapBiomas Agua Bolivia (deducidos en sitios conocidos): 11 natural,
# 22 represa o reservorio (Misicuni), 23 otra agua artificial (estanques), 24 poza minera (Tipuani)
WATER_TYPES = {"artificial_water_ha": [21, 22, 23], "mining_water_ha": [24], "natural_water_ha": [11, 12, 13, 14]}
_mbw_cache: dict = {}


def mapbiomas_water(basin, key):
    """Hectareas por ano de agua artificial, pozas mineras y agua natural (MapBiomas Agua, 1985-2024)."""
    ck = id(basin)
    if ck not in _mbw_cache:
        img = ee.Image(MB_WATER)
        codes = sum(WATER_TYPES.values(), [])
        groups = sum(([i] * len(v) for i, v in enumerate(WATER_TYPES.values())), [])
        rows = []
        for y in range(1985, 2025):
            cls = img.select(f"classification_{y}").remap(codes, groups, -1)
            g = retry(lambda: HA().addBands(cls).updateMask(cls.gte(0))
                      .reduceRegion(ee.Reducer.sum().group(1, "k"), basin, S(30), maxPixels=1e11, tileScale=4)
                      .get("groups").getInfo())
            row = {"year": y, **{k: 0.0 for k in WATER_TYPES}}
            for x in g:
                row[list(WATER_TYPES)[x["k"]]] = x["sum"]
            rows.append(row)
        _mbw_cache.clear()
        _mbw_cache[ck] = pd.DataFrame(rows)
    return _mbw_cache[ck][["year", key]].rename(columns={key: "value"})


SUSPECTS = {
    "forest_loss_ha": forest_loss,
    "burned_ha": burned,
    "dry_crop_ha": dry_crops,
    "mining_ha": lambda b: mapbiomas(b, "mining_ha"),
    "urban_ha": lambda b: mapbiomas(b, "urban_ha"),
    "pasture_ha": lambda b: mapbiomas(b, "pasture_ha"),
    "agri_ha": lambda b: mapbiomas(b, "agri_ha"),
    "night_lights": night_lights,
    "population": population,
    "artificial_water_ha": lambda b: mapbiomas_water(b, "artificial_water_ha"),
    "mining_water_ha": lambda b: mapbiomas_water(b, "mining_water_ha"),
}
# no es sospechoso: agua natural de toda el area, para el grafico de tendencias opuestas
CONTEXT_SERIES = {"natural_water_ha": lambda b: mapbiomas_water(b, "natural_water_ha")}
FLOW_SUSPECTS = {"forest_loss_ha", "burned_ha"}


# ------------------------------------------------------------------ imagenes
def download(url, path: Path):
    with urllib.request.urlopen(url, timeout=300) as r:
        path.write_bytes(r.read())


def images(body_id, area, out: Path, years):
    region = area.bounds()
    for y in years:
        p = out / f"{body_id}_{y}.png"
        if p.exists():
            continue
        log(f"   imagen {y}")
        try:
            url = landsat_vis(landsat_dry(y, region)).getThumbURL(
                {"region": region, "dimensions": 900, "format": "png"})
            download(url, p)
            if y <= JRC_LAST:
                wc = ee.ImageCollection(DS["jrc_yearly"]).filter(ee.Filter.eq("year", y)).first().select("waterClass")
                wurl = wc.gte(2).selfMask().visualize(palette=["1e88e5"]).getThumbURL(
                    {"region": region, "dimensions": 900, "format": "png"})
                download(wurl, out / f"{body_id}_{y}_water.png")
        except Exception as e:  # una imagen fallida no detiene la extraccion
            log(f"   no se pudo la imagen {y}: {e}")


# ------------------------------------------------------------------ main
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--config", default=str(ROOT / "config" / "bodies.csv"))
    ap.add_argument("--out", default=str(ROOT / "data" / "real"))
    ap.add_argument("--only", default="")
    ap.add_argument("--skip-images", action="store_true")
    ap.add_argument("--skip-suspects", default="", help="ej. dry_crop_ha,urban_ha")
    ap.add_argument("--climate", choices=["power", "chirps"], default="power")
    ap.add_argument("--water", choices=["landsat", "jrc"], default="landsat")
    a = ap.parse_args(argv)

    ee.Initialize(project=a.project)
    out = Path(a.out)
    (out / "img").mkdir(parents=True, exist_ok=True)

    log("ONI de NOAA")
    with urllib.request.urlopen(ONI_URL, timeout=60) as r:
        oni_raw = pd.read_csv(io.StringIO(r.read().decode()), sep=r"\s+")
    oni = oni_raw.groupby("YR")["ANOM"].mean().rename("oni").reset_index().rename(columns={"YR": "year"})
    oni.to_csv(out / "oni.csv", index=False)

    power = None
    if a.climate == "power":
        if not (out / "nasa_power.csv").exists():
            from uma import nasa_power
            nasa_power.main()
        power = pd.read_csv(out / "nasa_power.csv")

    cfg = pd.read_csv(a.config, dtype={"control_id": str}).fillna({"control_id": ""})
    if a.only:
        cfg = cfg[cfg.body_id.isin(a.only.split(","))]
    skip = set(filter(None, a.skip_suspects.split(",")))

    # resultados previos: se reemplazan solo los cuerpos de agua procesados ahora
    def _old(name):
        f = out / name
        return pd.read_csv(f) if f.exists() else pd.DataFrame()
    old_series, old_sus, old_check = _old("series.csv"), _old("suspects.csv"), _old("check.csv")

    series, suspects, checks = [], [], []
    for _, b in cfg.iterrows():
        log(f"\n== {b['name']} ({b.body_id})")
        pt = ee.Geometry.Point([b.lon, b.lat])
        area = pt.buffer(float(b.radius_km) * 1000)
        basin = basin_for(pt).union(area, 100)

        max_ha = retry(lambda: HA().updateMask(ee.Image(DS["jrc"]).select("max_extent"))
                       .reduceRegion(ee.Reducer.sum(), area, 30, maxPixels=1e11, tileScale=4).get("area").getInfo())
        basin_km2 = retry(lambda: basin.area(100).divide(1e6).getInfo())
        checks.append({"body_id": b.body_id, "max_water_ha": round(max_ha or 0), "basin_km2": round(basin_km2)})
        log(f"   agua maxima JRC en el area: {max_ha or 0:,.0f} ha · cuenca {basin_km2:,.0f} km2")

        log("   agua por ano (JRC, validacion)")
        jrc = water_series(area)
        jrc.loc[jrc.nodata_pct > 20, "water_ha"] = None
        if a.water == "landsat":
            log("   agua por ano (Landsat MNDWI)")
            w = water_landsat(area)
            w = w.merge(jrc[["year", "water_ha"]].rename(columns={"water_ha": "water_ha_jrc"}), on="year", how="left")
        else:
            w = jrc
        w.loc[w.nodata_pct > 20, "water_ha"] = None  # anos con muchos huecos subestiman el agua
        w["water_imputed"] = w.water_ha.isna()
        w["water_ha"] = w["water_ha"].interpolate(limit_area="inside")
        w["water_status"] = "observed"
        w.loc[w.water_imputed & w.water_ha.notna(), "water_status"] = "interpolated"
        w.loc[w.water_ha.isna(), "water_status"] = "unavailable"
        if "water_ha_jrc" in w:
            both = w.dropna(subset=["water_ha_jrc"])
            if len(both) > 5:
                log(f"   Landsat vs JRC: r = {both.water_ha.corr(both.water_ha_jrc):.2f}")
        if power is not None:
            log("   clima NASA POWER")
            clim = power[power.body_id == b.body_id][["year", "precip_mm", "temp_c"]]
        else:
            log("   lluvia (CHIRPS) y temperatura (ERA5-Land)")
            clim = climate_series(basin)
        s = w.merge(clim, on="year").merge(oni, on="year", how="left")
        try:
            log("   agua subterranea (GRACE)")
            s = s.merge(groundwater(basin), on="year", how="left")
        except Exception as e:
            log(f"   fallo GRACE: {e}")
        s.insert(0, "body_id", b.body_id)
        series.append(s)

        for name, fn in SUSPECTS.items():
            if name in skip:
                continue
            log(f"   sospechoso {name}")
            try:
                d = fn(basin)
                v = d.set_index("year")["value"].astype(float).reindex(YEARS)
                status = pd.Series("observed", index=v.index)
                status.loc[v.isna()] = "unavailable"
                if "value_status" in d:
                    status = d.set_index("year").value_status.reindex(YEARS).fillna("unavailable")
                # Hansen omite años sin pérdida: cero solo dentro de cobertura conocida.
                if name == "forest_loss_ha":
                    zero = v.isna() & (v.index >= 2001) & (v.index <= 2024)
                    v.loc[zero] = 0.
                    status.loc[zero] = "zero_within_product_coverage"
                # No extender población, luz ni usos de suelo fuera de su cobertura.
                d = v.reset_index()
                d.columns = ["year", "value"]
                d["value_status"] = status.to_numpy()
                d.insert(0, "body_id", b.body_id)
                d.insert(2, "suspect", name)
                suspects.append(d)
            except Exception as e:
                log(f"   fallo {name}: {e}")

        if not a.skip_images:
            images(b.body_id, area, out / "img", IMG_YEARS)

        # guardar despues de cada cuerpo de agua: si algo falla no se pierde lo anterior
        done = set(cfg.body_id.iloc[: len(series)])
        def _merge(old, new):
            new = pd.concat(new) if new else pd.DataFrame()
            if not old.empty:
                old = old[~old.body_id.isin(done)]
            return pd.concat([old, new], ignore_index=True)
        _merge(old_series, series).to_csv(out / "series.csv", index=False)
        _merge(old_sus, suspects).to_csv(out / "suspects.csv", index=False)
        _merge(old_check, [pd.DataFrame(checks)]).to_csv(out / "check.csv", index=False)

    allcfg = pd.read_csv(a.config, dtype={"control_id": str}).fillna({"control_id": ""})
    have = set(pd.read_csv(out / "series.csv").body_id)
    allcfg[allcfg.body_id.isin(have)][["body_id", "name", "lat", "lon", "kind", "control_id", "department"]] \
        .to_csv(out / "bodies.csv", index=False)
    log(f"\nListo. Datos en {out}. Siguiente: python run_engine.py data/real 2000")


if __name__ == "__main__":
    sys.exit(main())
