"""
Predicción espacio-temporal de focos de calor y mapas de anomalías - Bolivia (MODIS 2000-2025)

Uso:
    pip install pandas numpy scipy matplotlib scikit-learn lightgbm geopandas
    python fuego_bolivia.py

Salidas (carpeta OUT_DIR):
    - serie_nacional_anomalias.png   serie mensual + meses anómalos
    - mapa_anomalia_clim_<año>.png   z-score vs climatología (2000-2020)
    - mapa_anomalia_modelo_<año>.png observado vs predicho por el modelo
    - mapa_pronostico_h<H>.png       pronóstico a H meses
    - mapa_3d.html                   MAPA 3D INTERACTIVO (página web autónoma, abre con doble clic)
    - *.csv con las grillas para abrir en QGIS / Excel
"""
import glob
import json
import os
import webbrowser
import warnings

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.ndimage import uniform_filter
from scipy.stats import spearmanr

warnings.filterwarnings("ignore")

# ============================== CONFIGURACIÓN ===============================
DATA_GLOB = "modis_*_Bolivia.csv"   # ruta a tus CSV (ej. "datos/modis_*_Bolivia.csv")
OUT_DIR = "salidas"
RES = 0.25                          # resolución de la grilla en grados (~28 km)
CONF_MIN = 50                       # confianza mínima de la detección
TERRA_ONLY = True                   # Terra solo => serie homogénea (Aqua entra en 2002)
MIN_TOTAL_FIRES = 20                # descarta celdas casi sin fuego en 25 años
HORIZONS = [1, 3, 6]                # meses hacia adelante a predecir
TRAIN_END, VAL_END = 2020, 2022     # train <=2020 | val 2021-22 | test >=2023
ANOM_YEAR = 2024                    # año para los mapas de anomalía
ANOM_MONTHS = [8, 9, 10]            # temporada crítica (ago-oct)
BASE_YEARS = (2000, 2020)           # período de referencia (climatología)
ENSO_CSV = None                     # opcional: CSV con columnas 'month' (YYYY-MM) y 'oni'
BOUNDARY = None                     # opcional: shapefile/geojson de Bolivia
OPEN_BROWSER = True                 # abre mapa_3d.html al terminar
# ===========================================================================

LAT0, LAT1, LON0, LON1 = -23.0, -9.5, -69.8, -57.3
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), OUT_DIR)
os.makedirs(OUT_DIR, exist_ok=True)


# ------------------------------- 1. CARGA ----------------------------------
def find_files():
    """Busca los CSV en: la ruta dada, la carpeta del script y la carpeta actual (con subcarpetas)."""
    here = os.path.dirname(os.path.abspath(__file__))
    name = os.path.basename(DATA_GLOB)
    tried = []
    for base in (None, here, os.getcwd()):
        if base is None:
            pats = [DATA_GLOB]
        else:
            pats = [os.path.join(base, DATA_GLOB), os.path.join(base, "**", name)]
        for pat in pats:
            tried.append(pat)
            files = sorted(set(glob.glob(pat, recursive=True)))
            if files:
                print(f"Datos encontrados en: {os.path.dirname(files[0])}")
                return files
    raise FileNotFoundError(
        "No encontré los CSV. Busqué en:\n  " + "\n  ".join(tried) +
        "\nPon en DATA_GLOB la ruta completa, ej. r'C:\\ruta\\modis_*_Bolivia.csv'")


def load_data():
    files = find_files()
    cols = ["latitude", "longitude", "acq_date", "satellite", "confidence", "type"]
    df = pd.concat([pd.read_csv(f, usecols=cols) for f in files], ignore_index=True)
    df["acq_date"] = pd.to_datetime(df["acq_date"])
    df = df[(df.confidence >= CONF_MIN) & (df.type == 0)]  # solo vegetación
    if TERRA_ONLY:
        df = df[df.satellite == "Terra"]
    df = df[df.latitude.between(LAT0, LAT1) & df.longitude.between(LON0, LON1)]
    print(f"{len(files)} archivos | {len(df):,} focos tras filtros "
          f"({df.acq_date.min().date()} a {df.acq_date.max().date()})")
    return df


def build_tensor(df):
    """Tensor A[t, lat, lon] con conteo de focos por mes y celda."""
    y0 = df.acq_date.dt.year.min()
    t = (df.acq_date.dt.year - y0) * 12 + df.acq_date.dt.month - 1
    T = int(t.max()) + 1
    nlat = int(np.ceil((LAT1 - LAT0) / RES))
    nlon = int(np.ceil((LON1 - LON0) / RES))
    ilat = ((df.latitude - LAT0) / RES).astype(int).clip(0, nlat - 1)
    ilon = ((df.longitude - LON0) / RES).astype(int).clip(0, nlon - 1)
    A = np.zeros((T, nlat, nlon), dtype=np.float32)
    np.add.at(A, (t.values, ilat.values, ilon.values), 1)
    months = pd.period_range(f"{y0}-01", periods=T, freq="M")
    lat_c = LAT0 + (np.arange(nlat) + 0.5) * RES
    lon_c = LON0 + (np.arange(nlon) + 0.5) * RES
    return A, months, lat_c, lon_c


# --------------------------- 2. FEATURES + MODELO ---------------------------
def load_oni(months):
    if not ENSO_CSV:
        return None
    o = pd.read_csv(ENSO_CSV)
    o["month"] = pd.PeriodIndex(o["month"], freq="M")
    return o.set_index("month")["oni"].reindex(months).ffill().values


def make_dataset(A, months, lat_c, lon_c, mask, H, oni=None):
    """
    Objetivo: conteo de focos (regresión Poisson); las features van en log1p.
    Pronóstico directo a H meses: para predecir el mes t solo se usa
    información hasta t-H (sin fuga de datos). Devuelve filas para
    t en [t0, T+H): las últimas H son el futuro (y = NaN).
    """
    T = A.shape[0]
    Aext = np.concatenate([A, np.zeros((H,) + A.shape[1:], np.float32)])
    L = np.log1p(Aext)
    nbr = np.stack([uniform_filter(L[k], size=3, mode="constant") for k in range(len(L))])
    S = 12 * int(np.ceil(H / 12))        # mismo mes del año anterior, sin mirar al futuro
    t0 = max(H + 11, S)
    li, lj = np.where(mask)
    lat, lon = lat_c[li], lon_c[lj]
    month_of = np.array([m.month for m in months] +
                        [(months[-1] + k + 1).month for k in range(H)])
    out = []
    for t in range(t0, T + H):
        b = t - H
        d = {
            "t": np.full(len(li), t),
            "ci": li, "cj": lj, "lat": lat, "lon": lon,
            "lag_h": L[b][li, lj], "lag_h1": L[b - 1][li, lj], "lag_h2": L[b - 2][li, lj],
            "roll3": L[b - 2:b + 1].mean(0)[li, lj],
            "roll12": L[b - 11:b + 1].mean(0)[li, lj],
            "season": L[t - S][li, lj],
            "nbr": nbr[b][li, lj], "nbr_season": nbr[t - S][li, lj],
            "m_sin": np.full(len(li), np.sin(2 * np.pi * month_of[t] / 12)),
            "m_cos": np.full(len(li), np.cos(2 * np.pi * month_of[t] / 12)),
            "y": Aext[t][li, lj] if t < T else np.full(len(li), np.nan),
        }
        if oni is not None:
            d["oni"] = np.full(len(li), oni[b])
        out.append(pd.DataFrame(d))
    return pd.concat(out, ignore_index=True)


def make_model():
    try:
        import lightgbm as lgb
        return lgb.LGBMRegressor(objective="poisson", n_estimators=2000, learning_rate=0.03, num_leaves=63,
                                 min_child_samples=50, subsample=0.8, subsample_freq=1,
                                 colsample_bytree=0.8, random_state=42, verbose=-1), "lgb"
    except ImportError:
        from sklearn.ensemble import HistGradientBoostingRegressor
        return HistGradientBoostingRegressor(loss="poisson", max_iter=400, learning_rate=0.05, random_state=42), "sk"


def fit_predict(ds, years_of_t):
    feats = [c for c in ds.columns if c not in ("t", "ci", "cj", "y")]
    yr = ds["t"].map(years_of_t)
    tr = (yr <= TRAIN_END) & ds.y.notna()
    va = (yr > TRAIN_END) & (yr <= VAL_END) & ds.y.notna()
    model, kind = make_model()
    if kind == "lgb":
        import lightgbm as lgb
        model.fit(ds.loc[tr, feats], ds.loc[tr, "y"],
                  eval_set=[(ds.loc[va, feats], ds.loc[va, "y"])],
                  callbacks=[lgb.early_stopping(100, verbose=False)])
    else:
        model.fit(ds.loc[tr, feats], ds.loc[tr, "y"])
    ds = ds.copy()
    ds["pred"] = np.clip(model.predict(ds[feats]), 0, None)  # conteo esperado de focos
    return model, feats, ds


def evaluate(ds, years_of_t, H):
    yr = ds["t"].map(years_of_t)
    te = (yr > VAL_END) & ds.y.notna()
    d = ds[te]
    obs, pred, base = d.y, d.pred, np.expm1(d.season)
    nat = d.assign(o=obs, p=pred, b=base).groupby("t")[["o", "p", "b"]].sum()
    last_year = ds.loc[ds.y.notna(), "t"].map(years_of_t).max()
    print(f"\n--- Horizonte {H} mes(es) | test {VAL_END + 1}-{last_year} ---")
    print(f"Por celda-mes  MAE modelo: {np.abs(obs - pred).mean():.3f} | "
          f"MAE baseline estacional: {np.abs(obs - base).mean():.3f} | "
          f"Spearman: {spearmanr(obs, pred)[0]:.3f}")
    print(f"Total nacional mensual  MAE modelo: {np.abs(nat.o - nat.p).mean():.1f} | "
          f"baseline: {np.abs(nat.o - nat.b).mean():.1f} | corr: {np.corrcoef(nat.o, nat.p)[0, 1]:.3f}")
    return nat


# ------------------------------ 3. ANOMALÍAS --------------------------------
def climatology_anomaly(A, months, year, m_list):
    """z-score del conteo de la temporada vs. media/desvío del período base, por celda."""
    y0 = months[0].year
    idx = lambda y: [(y - y0) * 12 + m - 1 for m in m_list]
    obs = A[idx(year)].sum(0)
    base = np.stack([A[idx(y)].sum(0) for y in range(BASE_YEARS[0], BASE_YEARS[1] + 1)])
    mu, sd = base.mean(0), base.std(0, ddof=1)
    z = (obs - mu) / np.maximum.reduce([sd, np.sqrt(mu), np.ones_like(mu)])  # piso tipo Poisson
    z[~((mu >= 1) | (obs >= 3))] = np.nan
    return z, obs, mu


def national_anomalies(A, months):
    s = pd.Series(A.sum((1, 2)), index=months.to_timestamp())
    g = s.groupby(s.index.month)
    z = (s - g.transform("mean")) / g.transform("std")
    fig, ax = plt.subplots(2, 1, figsize=(13, 7), sharex=True)
    ax[0].plot(s.index, s.values, lw=1, color="#444")
    ax[0].set_ylabel("Focos / mes")
    ax[0].set_title("Focos de calor en Bolivia (MODIS)")
    ax[1].bar(s.index, z.values, width=25, color=np.where(z.values > 2, "#c0392b",
              np.where(z.values < -2, "#2471a3", "#aaa")))
    ax[1].axhline(2, ls="--", c="k", lw=.6); ax[1].axhline(-2, ls="--", c="k", lw=.6)
    ax[1].set_ylabel("z-score vs. mes climático")
    plt.tight_layout(); plt.savefig(f"{OUT_DIR}/serie_nacional_anomalias.png", dpi=150); plt.close()
    z.rename("z").to_csv(f"{OUT_DIR}/anomalia_nacional_mensual.csv")


# -------------------------------- 4. MAPAS ----------------------------------
def get_boundary():
    try:
        import geopandas as gpd
        if BOUNDARY:
            return gpd.read_file(BOUNDARY).to_crs(4326)
        w = gpd.read_file("https://naturalearth.s3.amazonaws.com/10m_cultural/ne_10m_admin_0_countries.zip")
        return w[w["ADMIN"] == "Bolivia"].to_crs(4326)
    except Exception as e:
        print(f"(sin límite de Bolivia: {type(e).__name__}; pasa BOUNDARY=ruta.shp)")
        return None


def plot_map(grid, lat_c, lon_c, title, fname, label, cmap="RdBu_r", vmin=None, vmax=None,
             boundary=None):
    fig, ax = plt.subplots(figsize=(7.5, 8.5))
    lon_e = np.r_[lon_c - RES / 2, lon_c[-1] + RES / 2]
    lat_e = np.r_[lat_c - RES / 2, lat_c[-1] + RES / 2]
    m = ax.pcolormesh(lon_e, lat_e, np.ma.masked_invalid(grid), cmap=cmap,
                      vmin=vmin, vmax=vmax, shading="flat")
    if boundary is not None:
        boundary.boundary.plot(ax=ax, color="k", lw=0.8)
    ax.set_xlim(LON0, LON1); ax.set_ylim(LAT0, LAT1); ax.set_aspect("equal")
    ax.set_xlabel("Longitud"); ax.set_ylabel("Latitud"); ax.set_title(title)
    plt.colorbar(m, ax=ax, shrink=0.75, label=label)
    plt.tight_layout(); plt.savefig(f"{OUT_DIR}/{fname}", dpi=150); plt.close()


def grid_to_csv(grid, lat_c, lon_c, name, col):
    ii, jj = np.where(~np.isnan(grid))
    pd.DataFrame({"lat": lat_c[ii], "lon": lon_c[jj], col: grid[ii, jj]}).to_csv(
        f"{OUT_DIR}/{name}.csv", index=False)


# ------------------------------ 5. PÁGINA WEB 3D -----------------------------
def boundary_rings(boundary):
    """Contorno de Bolivia como listas [lon, lat] (opcional, requiere geopandas)."""
    if boundary is None:
        return []
    try:
        g = boundary.geometry
        geom = g.union_all() if hasattr(g, "union_all") else g.unary_union
        geom = geom.simplify(0.02)
        polys = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
        return [[[round(x, 3), round(y, 3)] for x, y in p.exterior.coords] for p in polys]
    except Exception as e:
        print(f"(no se pudo extraer el contorno: {e})")
        return []


def export_web(A, months, lat_c, lon_c, mask, forecasts, model_anom, boundary):
    li, lj = np.where(mask)
    data = {
        "res": RES,
        "y0": int(months[0].year),
        "months": [str(m) for m in months],
        "lat": [round(float(v), 3) for v in lat_c[li]],
        "lon": [round(float(v), 3) for v in lon_c[lj]],
        "counts": np.clip(A[:, mask], 0, 65535).astype(int).ravel().tolist(),  # [mes][celda]
        "base": list(BASE_YEARS),
        "season": ANOM_MONTHS,
        "anom_year": ANOM_YEAR,
        "filters": f"confianza ≥ {CONF_MIN} · vegetación" + (" · solo Terra" if TERRA_ONLY else ""),
        "forecasts": [{"h": h, "month": m, "val": [round(float(v), 2) for v in vals]}
                      for h, m, vals in forecasts],
        "model_anom": model_anom,
        "boundary": boundary_rings(boundary),
    }
    html = WEB_TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    path = os.path.join(OUT_DIR, "mapa_3d.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Página web 3D: {path} ({len(html) / 1e6:.1f} MB)")
    return path


WEB_TEMPLATE = r'''<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Focos de calor en Bolivia · Mapa 3D</title>
<style>
:root{--bg:#0e1318;--panel:#161d25;--line:#26303b;--tx:#e8ebf0;--mut:#8d99a8;--ac:#ff7a3d}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--tx);font:14px/1.45 system-ui,"Segoe UI",Roboto,sans-serif;display:flex;flex-direction:column}
header{padding:10px 16px;border-bottom:1px solid var(--line)}
h1{font-size:18px;margin:0;font-weight:650}
header p{margin:2px 0 0;color:var(--mut);font-size:12px}
main{flex:1;display:flex;min-height:0}
#side{width:310px;flex:none;padding:14px;background:var(--panel);overflow:auto;border-right:1px solid var(--line)}
#stage{flex:1;position:relative;min-width:0;min-height:300px}
canvas#c{position:absolute;inset:0;width:100%;height:100%;cursor:grab;touch-action:none}
canvas#c.drag{cursor:grabbing}
label.t{display:block;color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.06em;margin:14px 0 4px}
label.t:first-child{margin-top:0}
select,button{width:100%;background:#1e2833;color:var(--tx);border:1px solid #33404e;border-radius:6px;padding:7px 8px;font:inherit}
button{cursor:pointer;width:auto}
button:hover{border-color:var(--ac)}
input[type=range]{width:100%;accent-color:var(--ac)}
.row{display:flex;gap:6px;align-items:center}
.row>*{flex:1}
#cur{font-size:20px;font-weight:650;margin:6px 0 2px}
#stats{color:var(--mut);font-size:12.5px;min-height:34px}
#legend{width:100%;height:14px;border-radius:3px;border:1px solid #33404e}
.lg{display:flex;justify-content:space-between;color:var(--mut);font-size:11px;margin-top:2px}
#spark{width:100%;height:70px;display:block;background:#11171d;border:1px solid var(--line);border-radius:6px;cursor:pointer}
#tip{position:absolute;pointer-events:none;background:#0b0f13ee;border:1px solid #3a4756;padding:5px 8px;border-radius:6px;font-size:12px;display:none;white-space:nowrap}
.hint{color:var(--mut);font-size:12px;margin-top:14px}
.views{display:flex;gap:6px;margin-top:6px}
.views button{flex:1;padding:6px 4px;font-size:12px}
@media(max-width:820px){main{flex-direction:column}#side{width:auto;border-right:0;border-bottom:1px solid var(--line);max-height:46vh}}
</style>
</head>
<body>
<header>
  <h1>Focos de calor en Bolivia · mapa 3D interactivo</h1>
  <p id="sub"></p>
</header>
<main>
  <div id="side">
    <label class="t" for="layer">Capa</label>
    <select id="layer"></select>
    <div id="sliderBox">
      <label class="t" for="k">Periodo</label>
      <input type="range" id="k" min="0" max="0" value="0">
      <div class="row" style="margin-top:6px"><button id="play">▶ Reproducir</button></div>
    </div>
    <div id="cur"></div>
    <div id="stats"></div>
    <label class="t">Escala de color</label>
    <canvas id="legend" width="280" height="14"></canvas>
    <div class="lg"><span id="lg0"></span><span id="lg1"></span><span id="lg2"></span></div>
    <div id="sparkBox">
      <label class="t">Total nacional (clic para saltar)</label>
      <canvas id="spark" width="280" height="70"></canvas>
    </div>
    <label class="t" for="ex">Exageración vertical</label>
    <input type="range" id="ex" min="0.4" max="3" step="0.1" value="1.2">
    <label class="t">Vista</label>
    <div class="views">
      <button data-v="obl">Oblicua</button><button data-v="top">Cenital</button>
      <button data-v="zin">＋</button><button data-v="zout">－</button>
    </div>
    <p class="hint">Arrastra para rotar · Mayús + arrastrar (o clic derecho) para mover · rueda para acercar.<br>
    Cada barra es una celda de <span id="resTxt"></span>°.</p>
    <p class="hint" id="notes"></p>
  </div>
  <div id="stage"><canvas id="c"></canvas><div id="tip"></div></div>
</main>

<script id="data" type="application/json">__DATA__</script>
<script>
(function(){
"use strict";
const D=JSON.parse(document.getElementById('data').textContent);
const N=D.lat.length,T=D.months.length,RES=D.res,Y0=D.y0;
const MES=['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'];
const cap=s=>s.charAt(0).toUpperCase()+s.slice(1);
const counts=Uint16Array.from(D.counts);
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));

/* ---------- geometría (unidades = celdas) ---------- */
let minLat=1e9,maxLat=-1e9,minLon=1e9,maxLon=-1e9;
for(let i=0;i<N;i++){minLat=Math.min(minLat,D.lat[i]);maxLat=Math.max(maxLat,D.lat[i]);minLon=Math.min(minLon,D.lon[i]);maxLon=Math.max(maxLon,D.lon[i]);}
const latMid=(minLat+maxLat)/2,lonMid=(minLon+maxLon)/2;
const CX=new Float32Array(N),CY=new Float32Array(N);
for(let i=0;i<N;i++){CX[i]=(D.lon[i]-lonMid)/RES;CY[i]=(D.lat[i]-latMid)/RES;}
const extX=(maxLon-minLon)/RES+1,extY=(maxLat-minLat)/RES+1;
const toXY=(lon,lat)=>[(lon-lonMid)/RES,(lat-latMid)/RES];
const CITIES=[['La Paz',-16.50,-68.15],['Santa Cruz',-17.78,-63.18],['Cochabamba',-17.39,-66.16],['Sucre',-19.04,-65.26],
 ['Trinidad',-14.83,-64.90],['Cobija',-11.03,-68.77],['Tarija',-21.53,-64.73],['Oruro',-17.97,-67.12],['Potosí',-19.58,-65.75]];

/* ---------- climatología ---------- */
const b0=D.base[0],b1=D.base[1];
const mu=new Float32Array(12*N),sd=new Float32Array(12*N);
for(let m=0;m<12;m++){
  const ts=[];for(let y=b0;y<=b1;y++){const t=(y-Y0)*12+m;if(t>=0&&t<T)ts.push(t);}
  const n=ts.length||1;
  for(let i=0;i<N;i++){let s=0,s2=0;for(const t of ts){const v=counts[t*N+i];s+=v;s2+=v*v;}
    const mean=s/n;mu[m*N+i]=mean;sd[m*N+i]=n>1?Math.sqrt(Math.max(0,(s2-n*mean*mean)/(n-1))):0;}
}
const zf=(x,m_,s_)=>(x-m_)/Math.max(s_,Math.sqrt(m_),1);

/* temporada (suma de meses D.season por año) */
const years=[];
for(let y=Y0;;y++){let ok=true;for(const m of D.season){if((y-Y0)*12+m-1>=T){ok=false;break;}}if(!ok)break;years.push(y);}
const SS=new Float32Array(years.length*N);
years.forEach((y,yi)=>{for(const m of D.season){const t=(y-Y0)*12+m-1;for(let i=0;i<N;i++)SS[yi*N+i]+=counts[t*N+i];}});
const sMu=new Float32Array(N),sSd=new Float32Array(N);
{const idx=[];years.forEach((y,yi)=>{if(y>=b0&&y<=b1)idx.push(yi);});const n=idx.length||1;
 for(let i=0;i<N;i++){let s=0,s2=0;for(const yi of idx){const v=SS[yi*N+i];s+=v;s2+=v*v;}
  const mean=s/n;sMu[i]=mean;sSd[i]=n>1?Math.sqrt(Math.max(0,(s2-n*mean*mean)/(n-1))):0;}}
const seasonName=D.season.length>1?`${MES[D.season[0]-1].slice(0,3)}–${MES[D.season[D.season.length-1]-1].slice(0,3)}`:MES[D.season[0]-1];

/* series nacionales */
const natM=new Float32Array(T);for(let t=0;t<T;t++){let s=0;for(let i=0;i<N;i++)s+=counts[t*N+i];natM[t]=s;}
const natS=new Float32Array(years.length);years.forEach((y,yi)=>{let s=0;for(let i=0;i<N;i++)s+=SS[yi*N+i];natS[yi]=s;});

/* escala de color de referencia (p99.5 de los conteos > 0) */
let VMAX;{const nz=[];for(let k=0;k<counts.length;k+=3)if(counts[k]>0)nz.push(counts[k]);nz.sort((a,b)=>a-b);VMAX=Math.max(5,nz[Math.floor(nz.length*0.995)]||5);}

/* ---------- capas ---------- */
const peak=natM.indexOf(Math.max(...natM));
const layers=[];
layers.push({name:'Focos observados (mensual)',n:T,mode:'seq',vmax:VMAX,unit:'focos',series:natM,start:peak,
  label:k=>`${cap(MES[k%12])} ${Y0+Math.floor(k/12)}`,
  val:k=>{const a=new Float32Array(N);for(let i=0;i<N;i++)a[i]=counts[k*N+i];return a;}});
layers.push({name:'Anomalía mensual (z vs climatología)',n:T,mode:'div',vmax:4,unit:'z',series:natM,start:peak,
  label:k=>`${cap(MES[k%12])} ${Y0+Math.floor(k/12)}`,
  val:k=>{const m=k%12,a=new Float32Array(N);for(let i=0;i<N;i++){const x=counts[k*N+i],m_=mu[m*N+i];
    a[i]=(m_>=0.3||x>=2)?zf(x,m_,sd[m*N+i]):0;}return a;}});
if(years.length){
  const ai=Math.max(0,years.indexOf(D.anom_year));
  layers.push({name:`Anomalía de temporada ${seasonName} (z por año)`,n:years.length,mode:'div',vmax:4,unit:'z',series:natS,start:ai,
    label:k=>`Temporada ${seasonName} ${years[k]}`,
    val:k=>{const a=new Float32Array(N);for(let i=0;i<N;i++){const x=SS[k*N+i];a[i]=(sMu[i]>=1||x>=3)?zf(x,sMu[i],sSd[i]):0;}return a;}});
}
if(D.forecasts&&D.forecasts.length){
  layers.push({name:'Pronóstico del modelo',n:D.forecasts.length,mode:'seq',vmax:VMAX,unit:'focos esperados',start:0,
    label:k=>{const f=D.forecasts[k];const [y,m]=f.month.split('-').map(Number);return `${cap(MES[m-1])} ${y} · a +${f.h} mes${f.h>1?'es':''}`;},
    val:k=>Float32Array.from(D.forecasts[k].val)});
}
if(D.model_anom){
  const v=D.model_anom.val.map(Math.abs).sort((a,b)=>a-b);const lim=Math.max(3,v[Math.floor(v.length*0.98)]||3);
  layers.push({name:'Anomalía vs modelo (observado − esperado)',n:1,mode:'div',vmax:lim,unit:'focos',start:0,
    label:()=>`Temporada ${seasonName} ${D.model_anom.year}`,val:()=>Float32Array.from(D.model_anom.val)});
}

/* ---------- UI ---------- */
const $=id=>document.getElementById(id);
$('sub').textContent=`MODIS (NASA FIRMS) · ${D.months[0]} a ${D.months[T-1]} · ${D.filters}`;
$('resTxt').textContent=RES;
$('notes').textContent=D.boundary&&D.boundary.length?'':'Referencias: ciudades principales (puntos blancos).';
layers.forEach((l,i)=>{const o=document.createElement('option');o.value=i;o.textContent=l.name;$('layer').appendChild(o);});
let L=layers[0],K=L.start,cur=null,playing=null,exag=1.2;
const HMAX=22;

function compute(){
  const val=L.val(K),h=new Float32Array(N),rgb=new Uint8ClampedArray(N*3);
  for(let i=0;i<N;i++){
    const v=val[i];let t,c;
    if(L.mode==='seq'){t=v<0.15?0:clamp(v/L.vmax,0,1);h[i]=Math.sqrt(t)*HMAX;c=seq(Math.sqrt(t));}
    else{t=clamp(Math.abs(v)/L.vmax,0,1);h[i]=t*HMAX;c=div(v/L.vmax);}
    rgb[i*3]=c[0];rgb[i*3+1]=c[1];rgb[i*3+2]=c[2];
  }
  cur={val,h,rgb};
  let tot=0,mx=-1e9,mi=0,hot=0;
  for(let i=0;i<N;i++){const v=val[i];tot+=v;if(v>mx){mx=v;mi=i;}if(L.mode==='div'&&v>2)hot++;}
  $('cur').textContent=L.label(K);
  const loc=`${D.lat[mi].toFixed(2)}°, ${D.lon[mi].toFixed(2)}°`;
  $('stats').innerHTML=L.mode==='seq'
    ? `Total: <b>${Math.round(tot).toLocaleString('es')}</b> ${L.unit}<br>Máximo: <b>${mx<10?mx.toFixed(1):Math.round(mx)}</b> en celda ${loc}`
    : `Celdas con z &gt; 2: <b>${hot}</b><br>Máximo: <b>${mx.toFixed(1)}</b> en celda ${loc}`;
  $('k').max=L.n-1;$('k').value=K;$('sliderBox').style.display=L.n>1?'block':'none';
  drawLegend();drawSpark();
  render();
}
const SEQ=[[255,245,176],[254,217,118],[253,141,60],[227,26,28],[128,0,38]];
function lerpStops(S,t){const p=clamp(t,0,1)*(S.length-1),i=Math.min(S.length-2,Math.floor(p)),f=p-i;
  return [0,1,2].map(j=>S[i][j]+(S[i+1][j]-S[i][j])*f);}
const seq=t=>lerpStops(SEQ,t);
const POS=[[247,222,205],[244,165,130],[214,96,77],[178,24,43]],NEG=[[215,230,243],[146,197,222],[67,147,195],[33,102,172]];
const div=t=>t>=0?lerpStops(POS,t):lerpStops(NEG,-t);
function drawLegend(){
  const g=$('legend'),x=g.getContext('2d'),w=g.width;
  for(let i=0;i<w;i++){const f=i/(w-1);let c;
    if(L.mode==='seq')c=seq(f);else c=div(f*2-1);
    x.fillStyle=`rgb(${c[0]|0},${c[1]|0},${c[2]|0})`;x.fillRect(i,0,1,g.height);}
  if(L.mode==='seq'){$('lg0').textContent='0';$('lg1').textContent=Math.round(L.vmax/4);$('lg2').textContent='≥ '+Math.round(L.vmax)+' '+L.unit;}
  else{$('lg0').textContent='−'+(+L.vmax.toFixed(1))+' (menos)';$('lg1').textContent='0';$('lg2').textContent='+'+(+L.vmax.toFixed(1))+' (más)';}
}
function drawSpark(){
  const box=$('sparkBox'),cv=$('spark');
  if(!L.series){box.style.display='none';return;}box.style.display='block';
  const x=cv.getContext('2d'),w=cv.width,h=cv.height,s=L.series,mx=Math.max(...s)||1;
  x.clearRect(0,0,w,h);x.strokeStyle='#ff9a63';x.lineWidth=1;x.beginPath();
  for(let i=0;i<s.length;i++){const px=s.length>1?i/(s.length-1)*(w-2)+1:w/2,py=h-3-(s[i]/mx)*(h-8);i?x.lineTo(px,py):x.moveTo(px,py);}
  x.stroke();
  const px=s.length>1?K/(s.length-1)*(w-2)+1:w/2;x.strokeStyle='#fff';x.beginPath();x.moveTo(px,0);x.lineTo(px,h);x.stroke();
}
$('spark').addEventListener('click',e=>{const r=e.target.getBoundingClientRect();setK(Math.round((e.clientX-r.left)/r.width*(L.n-1)));});
function setK(k){K=clamp(k|0,0,L.n-1);compute();}
$('layer').addEventListener('change',e=>{stop();L=layers[+e.target.value];K=L.start;compute();});
$('k').addEventListener('input',e=>setK(+e.target.value));
$('ex').addEventListener('input',e=>{exag=+e.target.value;render();});
function stop(){if(playing){clearInterval(playing);playing=null;$('play').textContent='▶ Reproducir';}}
$('play').addEventListener('click',()=>{
  if(playing){stop();return;}
  $('play').textContent='❚❚ Pausa';
  playing=setInterval(()=>{setK(K>=L.n-1?0:K+1);},L.n>60?90:450);
});

/* ---------- cámara y render 3D (proyección ortogonal) ---------- */
let yaw=-0.35,pitch=0.95,zoom=1,panX=0,panY=0,order=null,orderKey='';
const cv=$('c'),ctx=cv.getContext('2d'),tip=$('tip');
let W=0,H=0,dpr=1,scr=null;
function resize(){dpr=window.devicePixelRatio||1;W=cv.clientWidth;H=cv.clientHeight;cv.width=W*dpr;cv.height=H*dpr;render();}
window.addEventListener('resize',resize);
function render(){
  if(!cur||!W)return;
  ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,W,H);
  const cy=Math.cos(yaw),sy=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch);
  const R=Math.hypot(extX,extY)/2+HMAX*0.4;
  const S=Math.min(W,H)*0.95/(2*R)*zoom,ox=W/2+panX,oy=H/2+panY+HMAX*S*0.15;
  const P=(X,Y,Z)=>{const x1=X*cy-Y*sy,y1=X*sy+Y*cy;return [ox+x1*S,oy-(y1*sp+Z*cp)*S];};
  const key=yaw.toFixed(3)+pitch.toFixed(3);
  if(key!==orderKey||!order){const d=new Float32Array(N);for(let i=0;i<N;i++)d[i]=CX[i]*sy+CY[i]*cy;
    order=Array.from({length:N},(_,i)=>i).sort((a,b)=>d[b]-d[a]);orderKey=key;}
  const hs=.46;
  const poly=(pts,fill)=>{ctx.beginPath();ctx.moveTo(pts[0][0],pts[0][1]);for(let j=1;j<pts.length;j++)ctx.lineTo(pts[j][0],pts[j][1]);ctx.closePath();ctx.fillStyle=fill;ctx.fill();ctx.strokeStyle=fill;ctx.lineWidth=.6;ctx.stroke();};
  /* base */
  for(const i of order){const x=CX[i],y=CY[i];poly([P(x-hs,y-hs,0),P(x+hs,y-hs,0),P(x+hs,y+hs,0),P(x-hs,y+hs,0)],'#1b2430');}
  /* límite del país */
  if(D.boundary&&D.boundary.length){ctx.strokeStyle='#7e8fa3';ctx.lineWidth=1.2;
    for(const ring of D.boundary){ctx.beginPath();ring.forEach((p,j)=>{const q=toXY(p[0],p[1]),s=P(q[0],q[1],0);j?ctx.lineTo(s[0],s[1]):ctx.moveTo(s[0],s[1]);});ctx.stroke();}}
  /* barras */
  const vis=(nx,ny)=>(nx*sy+ny*cy)<0;
  const vS=vis(0,-1),vN=vis(0,1),vW=vis(-1,0),vE=vis(1,0);
  scr=new Float32Array(N*2);
  for(const i of order){
    const x=CX[i],y=CY[i],z=cur.h[i]*exag,r=cur.rgb[i*3],g=cur.rgb[i*3+1],b=cur.rgb[i*3+2];
    const t=P(x,y,z);scr[i*2]=t[0];scr[i*2+1]=t[1];
    if(z<0.05)continue;
    const fy=`rgb(${r*.62|0},${g*.62|0},${b*.62|0})`,fx=`rgb(${r*.78|0},${g*.78|0},${b*.78|0})`,ft=`rgb(${r|0},${g|0},${b|0})`;
    const x0=x-hs,x1=x+hs,y0=y-hs,y1=y+hs;
    if(vS)poly([P(x0,y0,0),P(x1,y0,0),P(x1,y0,z),P(x0,y0,z)],fy);
    if(vN)poly([P(x0,y1,0),P(x1,y1,0),P(x1,y1,z),P(x0,y1,z)],fy);
    if(vW)poly([P(x0,y0,0),P(x0,y1,0),P(x0,y1,z),P(x0,y0,z)],fx);
    if(vE)poly([P(x1,y0,0),P(x1,y1,0),P(x1,y1,z),P(x1,y0,z)],fx);
    poly([P(x0,y0,z),P(x1,y0,z),P(x1,y1,z),P(x0,y1,z)],ft);
  }
  /* ciudades */
  ctx.font='11px system-ui,sans-serif';ctx.textBaseline='middle';
  for(const c of CITIES){const q=toXY(c[2],c[1]),s=P(q[0],q[1],0);
    ctx.fillStyle='#fff';ctx.beginPath();ctx.arc(s[0],s[1],2.6,0,6.3);ctx.fill();
    ctx.lineWidth=3;ctx.strokeStyle='#0e1318';ctx.strokeText(c[0],s[0]+6,s[1]);ctx.fillStyle='#e8ebf0';ctx.fillText(c[0],s[0]+6,s[1]);}
  /* brújula */
  const nx=-sy,ny=-cy*sp,ln=Math.hypot(nx,ny)||1,bx=W-40,by=46;
  ctx.strokeStyle='#e8ebf0';ctx.fillStyle='#e8ebf0';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(bx,by);ctx.lineTo(bx+nx/ln*22,by+ny/ln*22);ctx.stroke();
  ctx.textAlign='center';ctx.fillText('N',bx+nx/ln*33,by+ny/ln*33);ctx.textAlign='start';
}
/* interacción */
let drag=null;
cv.addEventListener('contextmenu',e=>e.preventDefault());
cv.addEventListener('pointerdown',e=>{cv.setPointerCapture(e.pointerId);drag={x:e.clientX,y:e.clientY,pan:e.shiftKey||e.button!==0};cv.classList.add('drag');tip.style.display='none';});
cv.addEventListener('pointerup',()=>{drag=null;cv.classList.remove('drag');});
cv.addEventListener('pointermove',e=>{
  if(drag){const dx=e.clientX-drag.x,dy=e.clientY-drag.y;drag.x=e.clientX;drag.y=e.clientY;
    if(drag.pan){panX+=dx;panY+=dy;}else{yaw+=dx*0.008;pitch=clamp(pitch+dy*0.006,0.12,1.5);}render();return;}
  if(!scr)return;const r=cv.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top;
  let best=-1,bd=14*14;for(let i=0;i<N;i++){if(cur.h[i]<0.05&&Math.abs(cur.val[i])<1e-6)continue;const dx=scr[i*2]-mx,dy=scr[i*2+1]-my,d=dx*dx+dy*dy;if(d<bd){bd=d;best=i;}}
  if(best<0){tip.style.display='none';return;}
  const v=cur.val[best];
  tip.innerHTML=`${D.lat[best].toFixed(2)}°, ${D.lon[best].toFixed(2)}°<br><b>${L.mode==='seq'?(v<10?v.toFixed(1):Math.round(v)):(v>0?'+':'')+v.toFixed(2)}</b> ${L.unit}`;
  tip.style.left=(mx+14)+'px';tip.style.top=(my+14)+'px';tip.style.display='block';});
cv.addEventListener('pointerleave',()=>{tip.style.display='none';});
cv.addEventListener('wheel',e=>{e.preventDefault();zoom=clamp(zoom*(e.deltaY<0?1.1:1/1.1),0.4,6);render();},{passive:false});
document.querySelectorAll('.views button').forEach(b=>b.addEventListener('click',()=>{
  const v=b.dataset.v;
  if(v==='obl'){yaw=-0.35;pitch=0.95;zoom=1;panX=panY=0;}
  else if(v==='top'){yaw=0;pitch=1.5;zoom=1;panX=panY=0;}
  else if(v==='zin')zoom=clamp(zoom*1.25,0.4,6);else zoom=clamp(zoom/1.25,0.4,6);
  render();}));
resize();compute();
})();
</script>
</body>
</html>
'''


# --------------------------------- MAIN -------------------------------------
def main():
    df = load_data()
    A, months, lat_c, lon_c = build_tensor(df)
    y0 = months[0].year
    mask = A.sum(0) >= MIN_TOTAL_FIRES
    print(f"Grilla {A.shape[1]}x{A.shape[2]} | celdas activas: {mask.sum()} | meses: {A.shape[0]}")
    oni = load_oni(months)
    boundary = get_boundary()

    # ---- Anomalías respecto a la climatología
    national_anomalies(A, months)
    z, obs, mu = climatology_anomaly(A, months, ANOM_YEAR, ANOM_MONTHS)
    tag = "-".join(map(str, ANOM_MONTHS))
    plot_map(z, lat_c, lon_c,
             f"Anomalía de focos {ANOM_YEAR} (meses {tag})\nvs. climatología {BASE_YEARS[0]}-{BASE_YEARS[1]}",
             f"mapa_anomalia_clim_{ANOM_YEAR}.png", "z-score", vmin=-4, vmax=4, boundary=boundary)
    grid_to_csv(z, lat_c, lon_c, f"anomalia_clim_{ANOM_YEAR}", "z")

    # ---- Modelo predictivo por horizonte
    forecasts, model_anom = [], None
    for H in HORIZONS:
        ds = make_dataset(A, months, lat_c, lon_c, mask, H, oni)
        t_year = pd.Series({t: y0 + t // 12 for t in range(A.shape[0] + H)})
        model, feats, ds = fit_predict(ds, t_year)
        evaluate(ds, t_year, H)

        # Pronóstico del mes futuro T-1+H (solo usa datos observados)
        T = A.shape[0]
        fut = ds[ds.t == T - 1 + H]
        g = np.full(mask.shape, np.nan, dtype=float)
        g[fut.ci.values, fut.cj.values] = fut.pred.values
        mes_fut = (months[-1] + H).strftime("%Y-%m")
        plot_map(g, lat_c, lon_c, f"Pronóstico de focos {mes_fut} (H={H})",
                 f"mapa_pronostico_h{H}.png", "focos esperados / celda", cmap="YlOrRd", boundary=boundary)
        grid_to_csv(g, lat_c, lon_c, f"pronostico_h{H}", "focos_esp")
        forecasts.append((H, mes_fut, g[mask]))

        # Anomalía del modelo (observado - esperado) en la temporada del año ANOM_YEAR
        if H == HORIZONS[0]:
            sel = ds[ds.t.isin([(ANOM_YEAR - y0) * 12 + m - 1 for m in ANOM_MONTHS])]
            res = sel.assign(o=sel.y, p=sel.pred).groupby(["ci", "cj"])[["o", "p"]].sum()
            g2 = np.full(mask.shape, np.nan)
            g2[res.index.get_level_values(0), res.index.get_level_values(1)] = (res.o - res.p).values
            lim = np.nanpercentile(np.abs(g2), 98)
            plot_map(g2, lat_c, lon_c,
                     f"Anomalía vs. modelo {ANOM_YEAR} (obs - esperado, H={H})",
                     f"mapa_anomalia_modelo_{ANOM_YEAR}.png", "focos observados - esperados",
                     vmin=-lim, vmax=lim, boundary=boundary)
            grid_to_csv(g2, lat_c, lon_c, f"anomalia_modelo_{ANOM_YEAR}", "obs_menos_esp")
            model_anom = {"year": ANOM_YEAR,
                          "val": [round(float(v), 2) for v in np.nan_to_num(g2[mask])]}

            if hasattr(model, "feature_importances_"):
                imp = pd.Series(model.feature_importances_, feats).sort_values(ascending=False)
                print("\nImportancia de variables:\n", imp.head(8))
    web = export_web(A, months, lat_c, lon_c, mask, forecasts, model_anom, boundary)
    print(f"\nListo. Resultados en {OUT_DIR}")
    if OPEN_BROWSER:
        webbrowser.open("file:///" + web.replace("\\", "/"))


if __name__ == "__main__":
    main()