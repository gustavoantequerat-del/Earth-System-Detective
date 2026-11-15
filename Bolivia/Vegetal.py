"""
Vegetación en Bolivia (NDVI 2000-2026): modelo de pronóstico, mapas de anomalías y mapa 3D web

Datos: ndvi_bolivia_desde_2000.csv (NDVI por unidad administrativa, mensual)
    vim     = NDVI medio del mes (típico 0-1, negativo en agua/suelo desnudo)
    vim_avg = promedio histórico de ese mes
    viq     = % del promedio (100 = normal)

Uso:
    pip install pandas numpy scipy matplotlib scikit-learn lightgbm geopandas
    python vegetacion_bolivia.py

Salidas (carpeta OUT_DIR, junto al script):
    - mapa_3d_vegetacion.html              MAPA 3D INTERACTIVO
    - serie_nacional_vegetacion.png        serie nacional mensual de NDVI y anomalías
    - mapa_anomalia_ndvi_<año>.png         anomalía % de la temporada elegida
    - mapa_anomalia_modelo_ndvi_<año>.png  observado - esperado por el modelo
    - mapa_pronostico_h<H>.png             pronóstico de NDVI y de anomalía a H meses
    - ndvi_mensual_unidades.csv            panel mensual limpio (unidad x mes)
    - pronostico_h<H>.csv
"""
import glob
import json
import os
import warnings
import webbrowser

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.collections import PatchCollection
from matplotlib.patches import Rectangle
from scipy.stats import spearmanr

warnings.filterwarnings("ignore")

# ============================== CONFIGURACIÓN ===============================
CSV_GLOB = "ndvi_bolivia*.csv"      # nombre (o ruta) del CSV
OUT_DIR = "salidas_vegetacion"
ADM_LEVEL = 1                       # 1 = departamentos (9) | 2 = provincias (~110)
HORIZONS = [1, 3, 6]                # meses hacia adelante a predecir
TRAIN_END, VAL_END = 2020, 2022     # train <=2020 | val 2021-22 | test >=2023
ANOM_YEAR = 2024                    # año para los mapas de anomalía
ANOM_MONTHS = [1, 2, 3]             # temporada (ene-mar = pleno período de lluvias)
ENSO_CSV = None                     # opcional: CSV con columnas 'month' (YYYY-MM) y 'oni'
BOUNDARY = None                     # opcional: shapefile/geojson de Bolivia
OPEN_BROWSER = True                 # abre mapa_3d_vegetacion.html al terminar
K_NEIGHBORS = 6                     # vecinos espaciales para las variables del modelo
PIXEL_DEG = 0.05                    # tamaño de pixel del dato
NDVI_FLOOR = 0.05                   # piso del denominador para el % de anomalía
# ===========================================================================

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, OUT_DIR)
os.makedirs(OUT_DIR, exist_ok=True)
LEVEL_NAME = {1: "departamentos", 2: "provincias"}.get(ADM_LEVEL, f"nivel {ADM_LEVEL}")


# ------------------------------- 1. CARGA ----------------------------------
def find_csv():
    name = os.path.basename(CSV_GLOB)
    tried = []
    for pat in (CSV_GLOB, os.path.join(HERE, CSV_GLOB), os.path.join(HERE, "**", name),
                os.path.join(os.getcwd(), "**", name)):
        tried.append(pat)
        files = sorted(set(glob.glob(pat, recursive=True)))
        if files:
            print(f"Datos: {files[0]}")
            return files[0]
    raise FileNotFoundError("No encontré el CSV. Busqué en:\n  " + "\n  ".join(tried) +
                            "\nPon la ruta completa en CSV_GLOB.")


def load_panel():
    """Devuelve P[t,u] NDVI mensual, A[t,u] promedio histórico mensual, meta de unidades."""
    cols = ["date", "adm_level", "adm_id", "PCODE", "n_pixels", "vim", "vim_avg", "viq",
            "zona", "departamento", "latitud", "longitud", "limite_version", "limite_valid_on"]
    df = pd.read_csv(find_csv(), usecols=lambda c: c in cols)
    df["date"] = pd.to_datetime(df["date"])
    df = df[df.adm_level == ADM_LEVEL].copy()
    if df.empty:
        raise ValueError(f"No hay filas con adm_level == {ADM_LEVEL}")

    # Puede haber varias filas (adm_id, date) por PCODE en el mismo mes.
    # Agrupamos directamente por PCODE + month, ponderando por n_pixels.
    df["w"] = df["n_pixels"].clip(lower=1)
    df["vw"], df["aw"] = df["vim"] * df["w"], df["vim_avg"] * df["w"]
    df["month"] = df["date"].dt.to_period("M")

    g = df.groupby(["PCODE", "month"], as_index=False).agg(
        w=("w", "sum"), vw=("vw", "sum"), aw=("aw", "sum"))
    g["vim"], g["vim_avg"] = g.vw / g.w, g.aw / g.w

    meta = df.groupby("PCODE").agg(name=("zona", "first"), dept=("departamento", "first"),
                                   lat=("latitud", "first"), lon=("longitud", "first"))
    meta["npix"] = g.groupby("PCODE")["w"].mean()
    meta = meta.sort_index()
    meta["half"] = 0.5 * np.sqrt(meta["npix"]) * PIXEL_DEG

    # Pivot directo por month + PCODE (ya no hay duplicados)
    P = g.pivot(index="month", columns="PCODE", values="vim")
    A = g.pivot(index="month", columns="PCODE", values="vim_avg")
    full = pd.period_range(P.index.min(), P.index.max(), freq="M")
    P, A = [x.reindex(full).reindex(columns=meta.index) for x in (P, A)]
    ok = P.notna().mean(axis=1) >= 0.9
    last = ok[ok].index.max()
    P, A = P.loc[:last], A.loc[:last]
    print(f"{len(meta)} unidades ({LEVEL_NAME}) | {len(P)} meses completos "
          f"({P.index[0]} a {P.index[-1]})")
    return P.values.astype(np.float32), A.values.astype(np.float32), P.index, meta


def climatology(A, months):
    mo = np.array([p.month for p in months])
    return np.stack([np.nanmean(A[mo == m], axis=0) for m in range(1, 13)])


def pct_anom(p, a, floor=NDVI_FLOOR):
    """% de anomalía con piso para valores pequeños de NDVI (suelo desnudo / agua)."""
    return (p - a) / np.maximum(np.abs(a), floor) * 100


# --------------------------- 2. FEATURES + MODELO ---------------------------
def neighbor_weights(meta):
    xy = meta[["lon", "lat"]].values
    d = np.hypot(xy[:, None, 0] - xy[None, :, 0], xy[:, None, 1] - xy[None, :, 1])
    np.fill_diagonal(d, np.inf)
    W = np.zeros_like(d)
    k = min(K_NEIGHBORS, len(meta) - 1)
    for i in range(len(meta)):
        W[i, np.argsort(d[i])[:k]] = 1.0 / k
    return W


def load_oni(months):
    if not ENSO_CSV:
        return None
    o = pd.read_csv(ENSO_CSV)
    o["month"] = pd.PeriodIndex(o["month"], freq="M")
    return o.set_index("month")["oni"].reindex(months).ffill().values


def make_dataset(P, A, months, meta, clim, W, H, oni=None):
    T, U = P.shape
    Pext = np.vstack([P, np.full((H, U), np.nan, np.float32)])
    mo = np.array([p.month for p in months] + [(months[-1] + k + 1).month for k in range(H)])
    Aall = clim[mo - 1]
    L = Pext
    nbr = np.nan_to_num(L, nan=0.0) @ W.T
    S = 12 * int(np.ceil(H / 12))
    t0 = max(H + 12, S)
    out = []
    for t in range(t0, T + H):
        b = t - H
        p3, a3 = np.nanmean(Pext[b - 2:b + 1], 0), np.nanmean(Aall[b - 2:b + 1], 0)
        p12, a12 = np.nanmean(Pext[b - 11:b + 1], 0), np.nanmean(Aall[b - 11:b + 1], 0)
        d = {
            "t": np.full(U, t), "u": np.arange(U), "lat": meta.lat.values, "lon": meta.lon.values,
            "lag_h": L[b], "lag_h1": L[b - 1], "lag_h2": L[b - 2],
            "roll3": np.nanmean(L[b - 2:b + 1], 0), "roll12": np.nanmean(L[b - 11:b + 1], 0),
            "season": L[t - S], "nbr": nbr[b], "nbr_season": nbr[t - S],
            "clim": Aall[t],
            "anom_h": Pext[b] - Aall[b],
            "anom3": p3 - a3,
            "anom12": p12 - a12,
            "m_sin": np.full(U, np.sin(2 * np.pi * mo[t] / 12)),
            "m_cos": np.full(U, np.cos(2 * np.pi * mo[t] / 12)),
            "y": Pext[t],
        }
        if oni is not None:
            d["oni"] = np.full(U, oni[b])
        out.append(pd.DataFrame(d))
    return pd.concat(out, ignore_index=True), Aall


def make_model():
    try:
        import lightgbm as lgb
        return lgb.LGBMRegressor(objective="regression", n_estimators=2000,
                                 learning_rate=0.03, num_leaves=15, min_child_samples=20,
                                 subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
                                 random_state=42, verbose=-1), "lgb"
    except ImportError:
        from sklearn.ensemble import HistGradientBoostingRegressor
        return HistGradientBoostingRegressor(loss="squared_error", max_iter=400,
                                             learning_rate=0.05, random_state=42), "sk"


def fit_predict(ds, year_of_t):
    feats = [c for c in ds.columns if c not in ("t", "u", "y")]
    yr = ds["t"].map(year_of_t)
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
    ds["pred"] = np.clip(model.predict(ds[feats]), -0.2, 1.0)
    return model, feats, ds


def evaluate(ds, Aall, year_of_t, H):
    d = ds[(ds.t.map(year_of_t) > VAL_END) & ds.y.notna()].copy()
    d["clim_v"] = Aall[d.t.values, d.u.values]
    last = d.t.map(year_of_t).max()
    mae_m, mae_c = (d.y - d.pred).abs().mean(), (d.y - d.clim_v).abs().mean()
    skill = 1 - ((d.y - d.pred) ** 2).mean() / ((d.y - d.clim_v) ** 2).mean()
    ca = spearmanr(d.pred - d.clim_v, d.y - d.clim_v)[0]
    print(f"\n--- Horizonte {H} mes(es) | test {VAL_END + 1}-{last} ---")
    print(f"MAE NDVI modelo: {mae_m:.3f} | MAE climatología: {mae_c:.3f} | "
          f"habilidad vs climatología (1-MSE/MSE_clim): {skill:+.3f} | "
          f"correlación de anomalías (Spearman): {ca:.3f}")
    return d


# -------------------------------- 3. MAPAS ----------------------------------
def plot_units(meta, vals, title, fname, label, cmap, vmin=None, vmax=None):
    fig, ax = plt.subplots(figsize=(7.5, 8.5))
    patches = [Rectangle((r.lon - r.half, r.lat - r.half), 2 * r.half, 2 * r.half) for r in meta.itertuples()]
    pc = PatchCollection(patches, cmap=cmap, edgecolor="#555", linewidths=0.3)
    pc.set_array(np.ma.masked_invalid(np.asarray(vals, float)))
    pc.set_clim(vmin, vmax)
    ax.add_collection(pc)
    ax.set_xlim(meta.lon.min() - meta.half.max() * 1.2, meta.lon.max() + meta.half.max() * 1.2)
    ax.set_ylim(meta.lat.min() - meta.half.max() * 1.2, meta.lat.max() + meta.half.max() * 1.2)
    ax.set_aspect("equal"); ax.set_xlabel("Longitud"); ax.set_ylabel("Latitud"); ax.set_title(title)
    plt.colorbar(pc, ax=ax, shrink=0.75, label=label)
    plt.tight_layout(); plt.savefig(os.path.join(OUT_DIR, fname), dpi=150); plt.close()


def national_series(P, A, months, meta):
    w = meta.npix.values
    wp = np.nansum(P * w, 1) / np.nansum(np.where(np.isnan(P), 0, w), 1)
    wa = np.nansum(A * w, 1) / np.nansum(np.where(np.isnan(A), 0, w), 1)
    an = pct_anom(wp, wa)
    idx = months.to_timestamp()
    fig, ax = plt.subplots(2, 1, figsize=(13, 7), sharex=True)
    ax[0].plot(idx, wp, lw=1, color="#1f5f99", label="NDVI mensual")
    ax[0].plot(idx, wa, lw=1, color="#999", ls="--", label="Promedio histórico")
    ax[0].set_ylabel("NDVI (media ponderada por área)"); ax[0].legend()
    ax[0].set_title(f"Vegetación (NDVI) en Bolivia ({LEVEL_NAME})")
    ax[1].bar(idx, an, width=25, color=np.where(an < 0, "#a6611a", "#018571"))
    ax[1].axhline(0, c="k", lw=.6)
    ax[1].set_ylabel("Anomalía % (marrón = menos vegetación / estrés hídrico)")
    plt.tight_layout(); plt.savefig(os.path.join(OUT_DIR, "serie_nacional_vegetacion.png"), dpi=150); plt.close()
    pd.DataFrame({"month": months.astype(str), "ndvi": wp, "promedio_ndvi": wa, "anomalia_pct": an}) \
        .to_csv(os.path.join(OUT_DIR, "anomalia_nacional_mensual.csv"), index=False)


# ------------------------------ 4. CONTORNO --------------------------------
BOLIVIA_FALLBACK = [
    [-69.65, -10.95], [-69.05, -11.05], [-68.35, -10.90], [-67.35, -10.40], [-66.35, -9.75],
    [-65.40, -9.75], [-65.10, -10.90], [-64.50, -11.60], [-63.40, -12.40], [-62.60, -12.80],
    [-61.80, -13.40], [-60.60, -14.20], [-59.80, -15.20], [-58.80, -16.10], [-58.20, -16.60],
    [-58.10, -19.90], [-59.80, -20.05], [-61.50, -20.60], [-62.60, -21.70], [-62.80, -22.10],
    [-64.20, -22.90], [-65.50, -22.90], [-66.90, -22.80], [-67.90, -22.30], [-68.60, -21.30],
    [-68.90, -19.80], [-69.00, -18.60], [-69.40, -17.30], [-69.60, -15.00], [-69.35, -13.00],
]


def get_boundary():
    try:
        import geopandas as gpd
        if BOUNDARY:
            return gpd.read_file(BOUNDARY).to_crs(4326)
        w = gpd.read_file("https://naturalearth.s3.amazonaws.com/10m_cultural/ne_10m_admin_0_countries.zip")
        return w[w["ADMIN"] == "Bolivia"].to_crs(4326)
    except Exception as e:
        print(f"(sin límite real de Bolivia: {type(e).__name__}; se usará contorno aproximado)")
        return None


def boundary_rings(boundary):
    if boundary is not None:
        try:
            g = boundary.geometry
            geom = g.union_all() if hasattr(g, "union_all") else g.unary_union
            geom = geom.simplify(0.02)
            polys = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
            rings = [[[round(float(x), 3), round(float(y), 3)] for x, y in p.exterior.coords]
                     for p in polys]
            if rings:
                print(f"Contorno de Bolivia: {len(rings)} anillo(s) desde geopandas")
                return rings
        except Exception as e:
            print(f"(no se pudo extraer el contorno: {e})")
    print("(usando contorno aproximado de Bolivia como respaldo)")
    return [BOLIVIA_FALLBACK]


# ------------------------------ 5. PÁGINA WEB 3D ----------------------------
def export_web(P, A, months, meta, forecasts, model_anom, boundary):
    enc = lambda M: [round(float(v), 3) if np.isfinite(v) else -999 for v in M.ravel()]
    data = {
        "source": "NDVI por unidad administrativa", "level_name": LEVEL_NAME,
        "months": [str(m) for m in months],
        "name": meta.name.tolist(), "dept": meta.dept.tolist(),
        "lat": [round(float(v), 4) for v in meta.lat], "lon": [round(float(v), 4) for v in meta.lon],
        "half": [round(float(v), 4) for v in meta.half],
        "P": enc(P), "A": enc(A), "season": ANOM_MONTHS, "anom_year": ANOM_YEAR,
        "ndvi_floor": NDVI_FLOOR,
        "forecasts": forecasts, "model_anom": model_anom,
        "boundary": boundary_rings(boundary),
    }
    html = WEB_TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    path = os.path.join(OUT_DIR, "mapa_3d_vegetacion.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Página web 3D: {path} ({len(html) / 1e6:.1f} MB)")
    return path


WEB_TEMPLATE = r'''<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vegetación en Bolivia (NDVI) · Mapa 3D</title>
<style>
:root{--bg:#0e1318;--panel:#161d25;--line:#26303b;--tx:#e8ebf0;--mut:#8d99a8;--ac:#4aa3df}
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
  <h1>Vegetación en Bolivia (NDVI) · mapa 3D interactivo</h1>
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
      <label class="t">Promedio nacional (clic para saltar)</label>
      <canvas id="spark" width="280" height="70"></canvas>
    </div>
    <label class="t" for="an">Anchura celdas (horizontal)</label>
    <input type="range" id="an" min="0.05" max="1.5" step="0.05" value="0.55">
    <label class="t" for="ex">Altura de barras (vertical)</label>
    <input type="range" id="ex" min="0.4" max="3" step="0.1" value="1.2">
    <label class="t" for="ba">Opacidad bases</label>
    <input type="range" id="ba" min="0" max="1" step="0.05" value="0.5">
    <label class="t">Vista</label>
    <div class="views">
      <button data-v="obl">Oblicua</button><button data-v="top">Cenital</button>
      <button data-v="zin">＋</button><button data-v="zout">－</button>
    </div>
    <p class="hint">Arrastra para rotar · Mayús + arrastrar (o clic derecho) para mover · rueda para acercar.</p>
    <p class="hint">Cada barra es una unidad administrativa (<span id="lvl"></span>). El contorno del país viene de geopandas/Natural Earth; si no, se usa uno aproximado.</p>
    <p class="hint">Anomalía % = (NDVI − promedio) ÷ promedio. Denominador mínimo 0.05 (suelo desnudo/agua) para evitar cifras extremas. Marrón = menos vegetación / estrés hídrico · Verde = más vegetación.</p>
  </div>
  <div id="stage"><canvas id="c"></canvas><div id="tip"></div></div>
</main>

<script id="data" type="application/json">__DATA__</script>
<script>
(function(){
"use strict";
const D=JSON.parse(document.getElementById('data').textContent);
const U=D.name.length,T=D.months.length;
const MES=['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'];
const cap=s=>s.charAt(0).toUpperCase()+s.slice(1);
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
const MY=D.months.map(s=>s.split('-').map(Number));
const P=Float32Array.from(D.P,v=>v===-999?NaN:v);
const A=Float32Array.from(D.A,v=>v===-999?NaN:v);
const FLR=D.ndvi_floor||0.05;
const pct=(p,a,fl)=>(p-a)/Math.max(Math.abs(a),fl)*100;

/* geometría en grados */
let minLat=1e9,maxLat=-1e9,minLon=1e9,maxLon=-1e9,maxH=0;
for(let i=0;i<U;i++){minLat=Math.min(minLat,D.lat[i]);maxLat=Math.max(maxLat,D.lat[i]);minLon=Math.min(minLon,D.lon[i]);maxLon=Math.max(maxLon,D.lon[i]);maxH=Math.max(maxH,D.half[i]);}
if(D.boundary&&D.boundary.length){for(const ring of D.boundary){for(const p of ring){minLon=Math.min(minLon,p[0]);maxLon=Math.max(maxLon,p[0]);minLat=Math.min(minLat,p[1]);maxLat=Math.max(maxLat,p[1]);}}}
const latMid=(minLat+maxLat)/2,lonMid=(minLon+maxLon)/2;
const CX=new Float32Array(U),CY=new Float32Array(U),HS=new Float32Array(U),WT=new Float32Array(U);
for(let i=0;i<U;i++){CX[i]=D.lon[i]-lonMid;CY[i]=D.lat[i]-latMid;HS[i]=D.half[i]*0.94;WT[i]=D.half[i]*D.half[i];}
const extX=(maxLon-minLon)+2*maxH,extY=(maxLat-minLat)+2*maxH;
const HMAX=0.36*Math.max(extX,extY);
const toXY=(lon,lat)=>[lon-lonMid,lat-latMid];
const CITIES=[['La Paz',-16.50,-68.15],['Santa Cruz',-17.78,-63.18],['Cochabamba',-17.39,-66.16],['Sucre',-19.04,-65.26],
 ['Trinidad',-14.83,-64.90],['Cobija',-11.03,-68.77],['Tarija',-21.53,-64.73],['Oruro',-17.97,-67.12],['Potosí',-19.58,-65.75]];

let BOUNDARY_XY=[];

function wmean(a){let s=0,w=0;for(let i=0;i<U;i++){if(!isNaN(a[i])){s+=a[i]*WT[i];w+=WT[i];}}return w?s/w:NaN;}
const mlabel=k=>`${cap(MES[MY[k][1]-1])} ${MY[k][0]}`;

const layers=[];
const monthVal=k=>{const a=new Float32Array(U);for(let i=0;i<U;i++)a[i]=P[k*U+i];return a;};
const monthPct=k=>{const a=new Float32Array(U);for(let i=0;i<U;i++)a[i]=pct(P[k*U+i],A[k*U+i],FLR);return a;};
const tri=k=>{const a=new Float32Array(U);if(k<2){a.fill(NaN);return a;}
  for(let i=0;i<U;i++){let p=0,q=0;for(let j=0;j<3;j++){p+=P[(k-j)*U+i];q+=A[(k-j)*U+i];}a[i]=pct(p/3,q/3,FLR);}return a;};
const years=[];{const y0=MY[0][0],y1=MY[T-1][0];
  for(let y=y0;y<=y1;y++){const ok=D.season.every(m=>{const k=MY.findIndex(x=>x[0]===y&&x[1]===m);return k>=0;});if(ok)years.push(y);}}
const seasonVal=yi=>{const y=years[yi],a=new Float32Array(U);
  for(let i=0;i<U;i++){let p=0,q=0;for(const m of D.season){const k=MY.findIndex(x=>x[0]===y&&x[1]===m);p+=P[k*U+i];q+=A[k*U+i];}a[i]=pct(p/D.season.length,q/D.season.length,FLR);}return a;};
const seasonName=D.season.length>1?`${MES[D.season[0]-1].slice(0,3)}–${MES[D.season[D.season.length-1]-1].slice(0,3)}`:MES[D.season[0]-1];
const series=(n,f)=>{const s=new Float32Array(n);for(let k=0;k<n;k++)s[k]=wmean(f(k));return s;};

let start=MY.findIndex(x=>x[0]===D.anom_year&&x[1]===D.season[0]);if(start<0)start=T-1;

layers.push({name:'NDVI mensual (valor absoluto)',n:T,mode:'seq',vmax:0.9,unit:'NDVI',start,label:mlabel,val:monthVal,series:series(T,monthVal)});
layers.push({name:'Anomalía mensual (% vs promedio)',n:T,mode:'div',vmax:60,unit:'%',start,label:mlabel,val:monthPct,series:series(T,monthPct)});
layers.push({name:'Anomalía trimestral (% vs promedio, 3 meses)',n:T,mode:'div',vmax:60,unit:'%',start:Math.max(start,2),
  label:k=>'3 meses hasta '+mlabel(k),val:tri,series:series(T,tri)});
if(years.length){const ai=Math.max(0,years.indexOf(D.anom_year));
  layers.push({name:`Anomalía de temporada ${seasonName} (% por año)`,n:years.length,mode:'div',vmax:60,unit:'%',start:ai,
    label:k=>`Temporada ${seasonName} ${years[k]}`,val:seasonVal,series:series(years.length,seasonVal)});}
if(D.forecasts&&D.forecasts.length){
  const fl=k=>{const f=D.forecasts[k],[y,m]=f.month.split('-').map(Number);return `${cap(MES[m-1])} ${y} · a +${f.h} mes${f.h>1?'es':''}`;};
  layers.push({name:'Pronóstico del modelo (NDVI)',n:D.forecasts.length,mode:'seq',vmax:0.9,unit:'NDVI',start:0,label:fl,val:k=>Float32Array.from(D.forecasts[k].val)});
  layers.push({name:'Pronóstico del modelo (anomalía %)',n:D.forecasts.length,mode:'div',vmax:60,unit:'%',start:0,label:fl,val:k=>Float32Array.from(D.forecasts[k].pct)});}
if(D.model_anom){const v=D.model_anom.val.map(Math.abs).sort((a,b)=>a-b);const lim=Math.max(0.05,v[Math.floor(v.length*0.98)]||0.05);
  layers.push({name:'Anomalía vs modelo (observado − esperado, NDVI)',n:1,mode:'div',vmax:lim,unit:'NDVI',start:0,
    label:()=>`Temporada ${seasonName} ${D.model_anom.year}`,val:()=>Float32Array.from(D.model_anom.val)});}

const $=id=>document.getElementById(id);
$('sub').textContent=`${D.source} · ${D.months[0]} a ${D.months[T-1]} · ${U} unidades`;
$('lvl').textContent=D.level_name;
layers.forEach((l,i)=>{const o=document.createElement('option');o.value=i;o.textContent=l.name;$('layer').appendChild(o);});
let L=layers[0],K=L.start,cur=null,playing=null;
let ancho=0.55, exag=1.2, baseAlpha=0.5;

const SEQ=[[255,255,217],[199,233,180],[116,196,118],[35,139,69],[0,68,27]];
const NEG=[[246,232,195],[223,194,125],[191,129,45],[140,81,10]],POS=[[199,234,229],[128,205,193],[53,151,143],[1,102,94]];
function lerpStops(S,t){const p=clamp(t,0,1)*(S.length-1),i=Math.min(S.length-2,Math.floor(p)),f=p-i;return [0,1,2].map(j=>S[i][j]+(S[i+1][j]-S[i][j])*f);}
const seq=t=>lerpStops(SEQ,t),div=t=>t>=0?lerpStops(POS,t):lerpStops(NEG,-t);
const fmt=(v)=>{
  if(L.unit==='NDVI') return v.toFixed(2)+' NDVI';
  return (v>0?'+':'')+(Math.abs(v)<10?v.toFixed(1):Math.round(v))+' '+L.unit;
};

function compute(){
  const val=L.val(K),h=new Float32Array(U),rgb=new Uint8ClampedArray(U*3);
  for(let i=0;i<U;i++){const v=val[i];let c;
    if(isNaN(v)){h[i]=0;c=[40,48,58];}
    else if(L.mode==='seq'){
      const t=clamp(v/Math.max(L.vmax,0.01),0,1);h[i]=Math.sqrt(t)*HMAX;c=seq(Math.sqrt(t));
    }
    else{const t=clamp(v/L.vmax,-1,1);h[i]=Math.abs(t)*HMAX;c=div(t);}
    rgb[i*3]=c[0];rgb[i*3+1]=c[1];rgb[i*3+2]=c[2];}
  cur={val,h,rgb};
  const m=wmean(val);let mx=-1e9,mn=1e9,imx=0,imn=0,low=0,high=0;
  for(let i=0;i<U;i++){const v=val[i];if(isNaN(v))continue;if(v>mx){mx=v;imx=i;}if(v<mn){mn=v;imn=i;}
    if(L.unit==='%'){if(v<-15)low++;if(v>15)high++;}}
  $('cur').textContent=L.label(K);
  const nm=i=>`${D.name[i]} (${D.dept[i]})`;
  if(L.mode==='seq'){
    $('stats').innerHTML=`Promedio (ponderado por área): <b>${m.toFixed(2)}</b> NDVI<br>Más vegetación: <b>${mx.toFixed(2)}</b> en ${nm(imx)}`;
  }else if(L.unit==='%'){
    $('stats').innerHTML=`Promedio: <b>${m>0?'+':''}${m.toFixed(0)}%</b> · más bajas (&lt;−15%): <b>${low}</b> · más altas (&gt;+15%): <b>${high}</b><br>Extremo bajo: ${nm(imn)} ${mn.toFixed(0)}%`;
  }else{
    $('stats').innerHTML=`Promedio: <b>${m>0?'+':''}${m.toFixed(2)}</b> NDVI<br>Extremos: ${nm(imn)} ${mn.toFixed(2)} · ${nm(imx)} +${mx.toFixed(2)}`;
  }
  $('k').max=L.n-1;$('k').value=K;$('sliderBox').style.display=L.n>1?'block':'none';
  drawLegend();drawSpark();render();
}
function drawLegend(){
  const g=$('legend'),x=g.getContext('2d'),w=g.width;
  for(let i=0;i<w;i++){const f=i/(w-1),c=L.mode==='seq'?seq(Math.sqrt(f)):div(f*2-1);x.fillStyle=`rgb(${c[0]|0},${c[1]|0},${c[2]|0})`;x.fillRect(i,0,1,g.height);}
  if(L.mode==='seq'){$('lg0').textContent='0.0';$('lg1').textContent=(L.vmax/2).toFixed(2);$('lg2').textContent='≥ '+L.vmax.toFixed(2);}
  else{const v=Math.round(L.vmax);$('lg0').textContent='−'+v+' (menos veg.)';$('lg1').textContent='0';$('lg2').textContent='+'+v+' (más veg.)';}
}
function drawSpark(){
  const box=$('sparkBox'),cv=$('spark');
  if(!L.series){box.style.display='none';return;}box.style.display='block';
  const x=cv.getContext('2d'),w=cv.width,h=cv.height,s=L.series;let mn=1e9,mx=-1e9;
  for(const v of s){if(!isNaN(v)){mn=Math.min(mn,v);mx=Math.max(mx,v);}}
  if(L.mode==='seq')mn=0;else{mn=Math.min(mn,0);mx=Math.max(mx,0);}
  const rg=(mx-mn)||1,Y=v=>h-4-(v-mn)/rg*(h-8),X=i=>s.length>1?i/(s.length-1)*(w-2)+1:w/2;
  x.clearRect(0,0,w,h);
  if(L.mode==='div'){x.strokeStyle='#445';x.beginPath();x.moveTo(0,Y(0));x.lineTo(w,Y(0));x.stroke();}
  x.strokeStyle='#6fb8ee';x.lineWidth=1;x.beginPath();let first=true;
  for(let i=0;i<s.length;i++){if(isNaN(s[i]))continue;first?x.moveTo(X(i),Y(s[i])):x.lineTo(X(i),Y(s[i]));first=false;}
  x.stroke();x.strokeStyle='#fff';x.beginPath();x.moveTo(X(K),0);x.lineTo(X(K),h);x.stroke();
}
$('spark').addEventListener('click',e=>{const r=e.target.getBoundingClientRect();setK(Math.round((e.clientX-r.left)/r.width*(L.n-1)));});
function setK(k){K=clamp(k|0,0,L.n-1);compute();}
$('layer').addEventListener('change',e=>{stop();L=layers[+e.target.value];K=L.start;compute();});
$('k').addEventListener('input',e=>setK(+e.target.value));
$('an').addEventListener('input',e=>{ancho=+e.target.value;render();});
$('ex').addEventListener('input',e=>{exag=+e.target.value;render();});
$('ba').addEventListener('input',e=>{baseAlpha=+e.target.value;render();});
function stop(){if(playing){clearInterval(playing);playing=null;$('play').textContent='▶ Reproducir';}}
$('play').addEventListener('click',()=>{if(playing){stop();return;}$('play').textContent='❚❚ Pausa';
  playing=setInterval(()=>{setK(K>=L.n-1?0:K+1);},L.n>60?90:450);});

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
  const P3=(X,Y,Z)=>{const x1=X*cy-Y*sy,y1=X*sy+Y*cy;return [ox+x1*S,oy-(y1*sp+Z*cp)*S];};
  const key=yaw.toFixed(3)+pitch.toFixed(3);
  if(key!==orderKey||!order){const d=new Float32Array(U);for(let i=0;i<U;i++)d[i]=CX[i]*sy+CY[i]*cy;
    order=Array.from({length:U},(_,i)=>i).sort((a,b)=>d[b]-d[a]);orderKey=key;}
  const poly=(pts,fill,alpha=1)=>{ctx.globalAlpha=alpha;ctx.beginPath();ctx.moveTo(pts[0][0],pts[0][1]);for(let j=1;j<pts.length;j++)ctx.lineTo(pts[j][0],pts[j][1]);ctx.closePath();ctx.fillStyle=fill;ctx.fill();ctx.strokeStyle=fill;ctx.lineWidth=.6;ctx.stroke();ctx.globalAlpha=1;};

  BOUNDARY_XY=[];
  if(D.boundary&&D.boundary.length){
    for(const ring of D.boundary){
      const pts=[];
      for(const p of ring){const q=toXY(p[0],p[1]);pts.push(P3(q[0],q[1],0));}
      BOUNDARY_XY.push(pts);
    }
  }

  for(const i of order){
    if(isNaN(cur.val[i]))continue;
    const x=CX[i],y=CY[i],hx=HS[i]*ancho,hy=HS[i];
    if(hx<=0.001)continue;
    poly([P3(x-hx,y-hy,0),P3(x+hx,y-hy,0),P3(x+hx,y+hy,0),P3(x-hx,y+hy,0)],'#1b2430',baseAlpha);
  }

  if(BOUNDARY_XY.length){
    ctx.strokeStyle='#8ac4e8';ctx.lineWidth=1.8;ctx.lineJoin='round';
    for(const pts of BOUNDARY_XY){
      ctx.beginPath();ctx.moveTo(pts[0][0],pts[0][1]);
      for(let j=1;j<pts.length;j++)ctx.lineTo(pts[j][0],pts[j][1]);
      ctx.closePath();ctx.stroke();
    }
  }

  const vis=(nx,ny)=>(nx*sy+ny*cy)<0;
  const vS=vis(0,-1),vN=vis(0,1),vW=vis(-1,0),vE=vis(1,0);
  scr=new Float32Array(U*2);
  for(const i of order){
    const x=CX[i],y=CY[i],hx=HS[i]*ancho,hy=HS[i],z=cur.h[i]*exag;
    const r=cur.rgb[i*3],g=cur.rgb[i*3+1],b=cur.rgb[i*3+2];
    const t=P3(x,y,z);scr[i*2]=t[0];scr[i*2+1]=t[1];
    if(z<0.002)continue;
    const fy=`rgb(${r*.62|0},${g*.62|0},${b*.62|0})`,fx=`rgb(${r*.78|0},${g*.78|0},${b*.78|0})`,ft=`rgb(${r|0},${g|0},${b|0})`;
    const x0=x-hx,x1=x+hx,y0=y-hy,y1=y+hy;
    if(vS)poly([P3(x0,y0,0),P3(x1,y0,0),P3(x1,y0,z),P3(x0,y0,z)],fy);
    if(vN)poly([P3(x0,y1,0),P3(x1,y1,0),P3(x1,y1,z),P3(x0,y1,z)],fy);
    if(vW)poly([P3(x0,y0,0),P3(x0,y1,0),P3(x0,y1,z),P3(x0,y0,z)],fx);
    if(vE)poly([P3(x1,y0,0),P3(x1,y1,0),P3(x1,y1,z),P3(x1,y0,z)],fx);
    poly([P3(x0,y0,z),P3(x1,y0,z),P3(x1,y1,z),P3(x0,y1,z)],ft);
  }

  ctx.font='11px system-ui,sans-serif';ctx.textBaseline='middle';
  for(const c of CITIES){const q=toXY(c[2],c[1]),s=P3(q[0],q[1],0);
    ctx.fillStyle='#fff';ctx.beginPath();ctx.arc(s[0],s[1],2.6,0,6.3);ctx.fill();
    ctx.lineWidth=3;ctx.strokeStyle='#0e1318';ctx.strokeText(c[0],s[0]+6,s[1]);ctx.fillStyle='#e8ebf0';ctx.fillText(c[0],s[0]+6,s[1]);}
  const nx=-sy,ny=-cy*sp,ln=Math.hypot(nx,ny)||1,bx=W-40,by=46;
  ctx.strokeStyle='#e8ebf0';ctx.fillStyle='#e8ebf0';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(bx,by);ctx.lineTo(bx+nx/ln*22,by+ny/ln*22);ctx.stroke();
  ctx.textAlign='center';ctx.fillText('N',bx+nx/ln*33,by+ny/ln*33);ctx.textAlign='start';
}
let drag=null;
cv.addEventListener('contextmenu',e=>e.preventDefault());
cv.addEventListener('pointerdown',e=>{cv.setPointerCapture(e.pointerId);drag={x:e.clientX,y:e.clientY,pan:e.shiftKey||e.button!==0};cv.classList.add('drag');tip.style.display='none';});
cv.addEventListener('pointerup',()=>{drag=null;cv.classList.remove('drag');});
cv.addEventListener('pointermove',e=>{
  if(drag){const dx=e.clientX-drag.x,dy=e.clientY-drag.y;drag.x=e.clientX;drag.y=e.clientY;
    if(drag.pan){panX+=dx;panY+=dy;}else{yaw+=dx*0.008;pitch=clamp(pitch+dy*0.006,0.12,1.5);}render();return;}
  if(!scr)return;const r=cv.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top;
  let best=-1,bd=18*18;for(let i=0;i<U;i++){const dx=scr[i*2]-mx,dy=scr[i*2+1]-my,d=dx*dx+dy*dy;if(d<bd){bd=d;best=i;}}
  if(best<0){tip.style.display='none';return;}
  const v=cur.val[best];
  tip.innerHTML=`<b>${D.name[best]}</b> · ${D.dept[best]}<br>${isNaN(v)?'sin dato':fmt(v)}`;
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
    P, A, months, meta = load_panel()
    T, U = P.shape
    clim = climatology(A, months)
    W = neighbor_weights(meta)
    oni = load_oni(months)
    boundary = get_boundary()
    y0, m0 = months[0].year, months[0].month
    year_of_t = pd.Series({t: y0 + (m0 - 1 + t) // 12 for t in range(T + max(HORIZONS) + 1)})
    idx_of = lambda y, m: (y - y0) * 12 + (m - 1) - (m0 - 1)

    long = pd.DataFrame({"PCODE": np.tile(meta.index, T), "unidad": np.tile(meta.name, T),
                         "departamento": np.tile(meta.dept, T),
                         "mes": np.repeat(months.astype(str), U), "ndvi": P.ravel(),
                         "promedio_ndvi": A.ravel(), "anomalia_pct": pct_anom(P, A).ravel()})
    long.to_csv(os.path.join(OUT_DIR, "ndvi_mensual_unidades.csv"), index=False)
    national_series(P, A, months, meta)

    ids = [idx_of(ANOM_YEAR, m) for m in ANOM_MONTHS]
    if all(0 <= i < T for i in ids):
        an = pct_anom(np.nanmean(P[ids], 0), np.nanmean(A[ids], 0))
        tag = "-".join(map(str, ANOM_MONTHS))
        plot_units(meta, an, f"Anomalía de NDVI {ANOM_YEAR} (meses {tag})\nvs. promedio histórico",
                   f"mapa_anomalia_ndvi_{ANOM_YEAR}.png", "% del promedio (marrón = menos vegetación)",
                   "BrBG", -60, 60)
    else:
        print(f"(ANOM_YEAR={ANOM_YEAR} no está completo en los datos; cambia ANOM_YEAR/ANOM_MONTHS)")

    forecasts, model_anom = [], None
    for H in HORIZONS:
        ds, Aall = make_dataset(P, A, months, meta, clim, W, H, oni)
        model, feats, ds = fit_predict(ds, year_of_t)
        evaluate(ds, Aall, year_of_t, H)

        fut = ds[ds.t == T - 1 + H].sort_values("u")
        ndvi = fut.pred.values
        pcn = pct_anom(ndvi, Aall[T - 1 + H][fut.u.values])
        mes_fut = str(months[-1] + H)
        forecasts.append({"h": H, "month": mes_fut,
                          "val": [round(float(v), 3) for v in ndvi],
                          "pct": [round(float(v), 1) for v in pcn]})
        plot_units(meta, ndvi, f"Pronóstico de NDVI {mes_fut} (H={H})", f"mapa_pronostico_h{H}.png",
                   "NDVI esperado", "YlGn", -0.1, 1.0)
        plot_units(meta, pcn, f"Pronóstico de anomalía {mes_fut} (H={H})", f"mapa_pronostico_anom_h{H}.png",
                   "% del promedio (marrón = estrés)", "BrBG", -60, 60)
        pd.DataFrame({"PCODE": meta.index, "unidad": meta.name.values, "mes": mes_fut,
                      "ndvi_esperado": ndvi, "anomalia_pct": pcn}).to_csv(
            os.path.join(OUT_DIR, f"pronostico_h{H}.csv"), index=False)

        if H == HORIZONS[0] and all(0 <= i < T for i in ids):
            sel = ds[ds.t.isin(ids)]
            res = sel.groupby("u")[["y", "pred"]].mean()
            diff = np.full(U, np.nan)
            diff[res.index.values] = (res.y - res.pred).values
            lim = np.nanpercentile(np.abs(diff), 98)
            plot_units(meta, diff, f"Anomalía vs modelo {ANOM_YEAR} (obs − esperado, H={H})",
                       f"mapa_anomalia_modelo_ndvi_{ANOM_YEAR}.png",
                       "NDVI (marrón = menos vegetación de la esperada)", "BrBG", -lim, lim)
            model_anom = {"year": ANOM_YEAR, "val": [round(float(v), 3) for v in np.nan_to_num(diff)]}
            if hasattr(model, "feature_importances_"):
                print("\nImportancia de variables:\n",
                      pd.Series(model.feature_importances_, feats).sort_values(ascending=False).head(8))

    web = export_web(P, A, months, meta, forecasts, model_anom, boundary)
    print(f"\nListo. Resultados en {OUT_DIR}")
    if OPEN_BROWSER:
        webbrowser.open("file:///" + web.replace("\\", "/"))


if __name__ == "__main__":
    main()