# backend/app/analysis.py
# Análisis por región extendido con series de anomalía, climatología y diagnóstico temporal.

import math

import numpy as np
import pandas as pd
import pymannkendall as mk
from scipy.stats import pearsonr

from .diagnosis import (
    compute_climatology_36,
    compute_windows,
    compute_worst_period,
)


def _trend(series: pd.Series) -> dict:
    s = series.dropna()
    if len(s) < 10:
        return {"slope": None, "p_value": None, "trend": "no_data",
                "significant": False, "n_obs": int(len(s))}
    r = mk.original_test(s.values)
    return {
        "slope":       float(r.slope),
        "p_value":     float(r.p),
        "trend":       r.trend,
        "significant": bool(r.h),
        "n_obs":       int(len(s)),
    }


def _lag_correlation(df: pd.DataFrame, max_lag: int = 3) -> dict:
    best = {"r": None, "p_value": None, "lag_dekads": None, "significant": False}
    r3h = df["r3h"].to_numpy()
    vim = df["vim"].to_numpy()
    for lag in range(0, max_lag + 1):
        a = r3h[: len(r3h) - lag] if lag else r3h
        b = vim[lag:]             if lag else vim
        mask = ~(np.isnan(a) | np.isnan(b))
        if mask.sum() < 10:
            continue
        r_val, p_val = pearsonr(a[mask], b[mask])
        if best["r"] is None or abs(r_val) > abs(best["r"]):
            best = {
                "r": float(r_val),
                "p_value": float(p_val),
                "lag_dekads": lag,
                "significant": bool(p_val < 0.05),
            }
    return best


def _classify(rain: dict, ndvi: dict) -> tuple[str, str]:
    rain_dec = rain["significant"] and rain["trend"] == "decreasing"
    ndvi_dec = ndvi["significant"] and ndvi["trend"] == "decreasing"
    if rain_dec and ndvi_dec:
        return "crisis", "CRISIS: Sequía significativa con impacto en vegetación"
    if rain_dec:
        return "alert", "ALERTA: Precipitación decreciente significativa"
    if ndvi_dec:
        return "watch", "INVESTIGAR: NDVI decreciente significativo"
    return "stable", "ESTABLE: Sin tendencias significativas a la baja"


def _series(df: pd.DataFrame, col: str) -> list[dict]:
    sub = df[["date", col]].dropna()
    return [{"date": d.strftime("%Y-%m-%d"), "value": float(v)}
            for d, v in zip(sub["date"], sub[col])]


def _explain(rain: dict, ndvi: dict, corr: dict) -> str:
    def _phrase(t, name):
        if t["p_value"] is None:
            return f"No hay suficientes datos de {name}."
        w = {"decreasing": "decreciente", "increasing": "creciente",
             "no trend": "sin tendencia"}.get(t["trend"], "sin tendencia")
        sig = "significativa" if t["significant"] else "no significativa"
        return f"{name} muestra una tendencia {w} {sig} (p={t['p_value']:.3f})."

    parts = [_phrase(rain, "La precipitación"), _phrase(ndvi, "El NDVI")]
    if corr["r"] is not None:
        sig = "significativa" if corr["significant"] else "no significativa"
        parts.append(
            f"Correlación máxima r={corr['r']:.2f} a {corr['lag_dekads']} "
            f"dekads de retraso ({sig})."
        )
    return " ".join(parts)


def analyze_region(pcode: str, data) -> dict | None:
    pcode = pcode.upper()
    if pcode not in data.by_pcode:
        return None

    df   = data.by_pcode[pcode]
    meta = data.meta[pcode]
    nm   = data.names.get(pcode, {"name": pcode, "adm1_name": ""})

    rain_t = _trend(df["r3h"])
    ndvi_t = _trend(df["vim"])
    corr   = _lag_correlation(df)
    level, verdict = _classify(rain_t, ndvi_t)

    # Diagnóstico temporal (puede devolver None si no hay anomalías).
    windows     = compute_windows(df)
    worst       = compute_worst_period(df, window_months=12)
    rain_clim, ndvi_clim = compute_climatology_36(df)

    rain_block = {
        "variable": "r3h", "unit": "mm",
        "series": _series(df, "r3h"),
        **rain_t,
        "anomaly_series": _series(df, "r3q"),
        "climatology": rain_clim,
    }
    ndvi_block = {
        "variable": "vim", "unit": "NDVI",
        "series": _series(df, "vim"),
        **ndvi_t,
        "anomaly_series": _series(df, "viq"),
        "climatology": ndvi_clim,
    }

    return {
        "pcode": pcode,
        "name": nm["name"],
        "adm1_name": nm["adm1_name"],
        "level": level,
        "verdict": verdict,
        "explanation": _explain(rain_t, ndvi_t, corr),
        "n_pixels": meta["n_pixels"],
        "period": {"start": meta["start"], "end": meta["end"]},
        "rainfall": rain_block,
        "ndvi": ndvi_block,
        "correlation": corr,
        "windows": windows,
        "worst_period": worst,
    }