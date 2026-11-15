from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import pandas as pd
import numpy as np
import pymannkendall as mk
from scipy.stats import pearsonr
from .timeseries import build_timeseries
import json

app = FastAPI(title="Earth System Trend Detective - Bolivia")

# Permitir que el frontend (React en otro puerto) llame al backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# 1. CARGA DE DATOS AL INICIO (una sola vez, no por request)
# ============================================================

print("Cargando datos...")

# --- Rainfall ---
rain = pd.read_csv("bol-rainfall-subnat-full.csv")
rain = rain[rain["version"] == "final"].copy()  # Ajusta el nombre de la columna si es necesario
rain["date"] = pd.to_datetime(rain["date"])   # en lugar de rain["date"]

# --- NDVI ---
ndvi = pd.read_csv("bol-ndvi-subnat-full.csv")
ndvi["date"] = pd.to_datetime(ndvi["date"])

# --- GeoJSON ADM2 ---
with open("bol_admin_boundaries.geojson/bol_admin2.geojson") as f:
    adm2_geojson = json.load(f)

print(f"Rainfall: {len(rain)} registros | NDVI: {len(ndvi)} registros | ADM2: {len(adm2_geojson['features'])} regiones")

# ============================================================
# 2. FUNCIONES DE ANÁLISIS
# ============================================================

def analyze_region(pcode: str) -> dict:
    """Ejecuta el análisis completo para una región (PCODE)."""
    
    rain_r = rain[rain["PCODE"] == pcode].sort_values("date").copy()
    ndvi_r = ndvi[ndvi["PCODE"] == pcode].sort_values("date").copy()
    
    if rain_r.empty or ndvi_r.empty:
        raise HTTPException(status_code=404, detail=f"Región {pcode} no encontrada en ambos datasets")
    
    # --- Merge por fecha (ambos son dekadales) ---
    merged = pd.merge(
        rain_r[["date", "r3h"]],   # Ajusta si la columna de precipitación 3-meses se llama distinto
        ndvi_r[["date", "vim"]],    # Ajusta si la columna de NDVI se llama distinto
        on="date",
        how="inner"
    ).dropna()
    
    if len(merged) < 30:
        raise HTTPException(status_code=422, detail=f"Datos insuficientes para {pcode} ({len(merged)} registros)")
    
    # --- Tendencias (Mann-Kendall) ---
    trend_rain = mk.original_test(merged["r3h"].values)
    trend_ndvi = mk.original_test(merged["vim"].values)
    
    # --- Correlación con lag (0 a 3 dekads = 0-30 días) ---
    best_lag, best_r, best_p = 0, 0.0, 1.0
    for lag in range(0, 4):
        shifted = merged["vim"].shift(-lag).dropna()
        if len(shifted) < 30:
            continue
        r, p = pearsonr(merged["r3h"].iloc[:len(shifted)], shifted)
        if abs(r) > abs(best_r):
            best_lag, best_r, best_p = lag, r, p
    
    # --- Veredicto combinado ---
    rain_sig = trend_rain.p < 0.05
    ndvi_sig = trend_ndvi.p < 0.05
    rain_dec = trend_rain.trend == "decreasing"
    ndvi_dec = trend_ndvi.trend == "decreasing"
    
    if rain_sig and ndvi_sig and rain_dec and ndvi_dec:
        verdict = "CRISIS: Sequía significativa con impacto en vegetación"
        level = "crisis"
    elif rain_sig and rain_dec:
        verdict = "ALERTA: Sequía significativa, impacto vegetal no confirmado"
        level = "alert"
    elif ndvi_sig and ndvi_dec:
        verdict = "INVESTIGAR: Estrés vegetal sin tendencia clara en lluvia"
        level = "watch"
    else:
        verdict = "ESTABLE: Sin tendencias significativas"
        level = "stable"
    
    return {
        "pcode": pcode,
        "series": {
            "dates": [d.strftime("%Y-%m-%d") for d in merged["date"]],
            "rainfall": [round(float(v), 2) for v in merged["r3h"]],
            "ndvi": [round(float(v), 4) for v in merged["vim"]],
        },
        "trend_rainfall": {
            "trend": trend_rain.trend,
            "slope": round(float(trend_rain.slope), 6),
            "p_value": round(float(trend_rain.p), 6),
            "significant": rain_sig,
        },
        "trend_ndvi": {
            "trend": trend_ndvi.trend,
            "slope": round(float(trend_ndvi.slope), 6),
            "p_value": round(float(trend_ndvi.p), 6),
            "significant": ndvi_sig,
        },
        "correlation": {
            "r": round(float(best_r), 4),
            "p_value": round(float(best_p), 6),
            "lag_dekads": best_lag,
            "significant": best_p < 0.05,
        },
        "verdict": verdict,
        "level": level,
    }

# ============================================================
# 3. ENDPOINTS
# ============================================================

@app.get("/api/regions")
def get_regions():
    """Devuelve el GeoJSON de ADM2 con metadata básica."""
    return adm2_geojson

@app.get("/api/regions/verdicts")
def get_all_verdicts():
    """Calcula el veredicto para TODAS las regiones (para el mapa de coropletas)."""
    results = []
    for feat in adm2_geojson["features"]:
        pcode = feat["properties"].get("PCODE") or feat["properties"].get("Pcode")
        if not pcode:
            continue
        try:
            r = analyze_region(pcode)
            results.append({
                "pcode": pcode,
                "name": feat["properties"].get("ADM2_EN") or feat["properties"].get("ADM2_ES", ""),
                "level": r["level"],
                "verdict": r["verdict"],
            })
        except HTTPException:
            results.append({"pcode": pcode, "level": "no_data", "verdict": "Sin datos suficientes"})
    return {"regions": results}

@app.get("/api/analysis/{pcode}")
def get_analysis(pcode: str):
    """Análisis completo para una región específica."""
    return analyze_region(pcode)

@app.get("/api/health")
def health():
    have_anom = any(
        df["r3q"].notna().any()
        for df in DATA.by_pcode.values()
    )
    return {
        "ok": True,
        "regions_total": len(DATA.names),
        "regions_with_data": len(DATA.by_pcode),
        "geojson_kb": len(_geojson_gz) // 1024,
        "anomalies_available": have_anom,  # ← NUEVO
    }


# … después de /api/analysis/{pcode}


# ============================================================
# 4. SERVIR EL FRONTEND (opcional: si compilas React en /dist)
# ============================================================

# app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="static")
# @app.get("/")
# def root():
#     return FileResponse("frontend/dist/index.html")