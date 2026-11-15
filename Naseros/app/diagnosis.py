# backend/app/diagnosis.py
# Funciones puras de diagnóstico temporal.
# Reglas:
#   score = 0.6 * A_r + 0.4 * A_v      (A_r = anomalía media lluvia %, A_v = anomalía media NDVI %)
#   extreme: score < -40 | high: < -25 | moderate: < -10 | low: >= -10

from __future__ import annotations

import math
from datetime import datetime

import numpy as np
import pandas as pd

SEVERITY_THRESHOLDS = [
    (-40.0, "extreme"),
    (-25.0, "high"),
    (-10.0, "moderate"),
]

# Ventanas por defecto: (label, meses)
DEFAULT_WINDOWS = [
    ("Últimos 6 meses", 6),
    ("Últimos 12 meses", 12),
    ("Últimos 24 meses", 24),
    ("Últimos 60 meses (5 años)", 60),
]


def score_severity(rain_anom_pct: float, ndvi_anom_pct: float) -> str:
    """Severidad compuesta con pesos 0.6 (lluvia) / 0.4 (NDVI)."""
    if not (math.isfinite(rain_anom_pct) and math.isfinite(ndvi_anom_pct)):
        return "low"
    score = 0.6 * rain_anom_pct + 0.4 * ndvi_anom_pct
    for thr, label in SEVERITY_THRESHOLDS:
        if score < thr:
            return label
    return "low"


def _mean_window(df: pd.DataFrame, col: str, months: int) -> float:
    end = df["date"].max()
    if pd.isna(end):
        return float("nan")
    start = end - pd.DateOffset(months=months)
    sub = df.loc[df["date"] >= start, col].dropna()
    if sub.empty:
        return float("nan")
    # Convertir ratio (100 = normal) a diferencia porcentual (0 = normal)
    return float(sub.mean() - 100.0)

def compute_windows(df: pd.DataFrame) -> list[dict]:
    """Devuelve una entrada por ventana DEFAULT_WINDOWS con severidad."""
    out = []
    end = df["date"].max()
    for label, months in DEFAULT_WINDOWS:
        start = end - pd.DateOffset(months=months)
        r = _mean_window(df, "r3q", months)
        v = _mean_window(df, "viq", months)
        out.append({
            "label": label,
            "start": start.strftime("%Y-%m-%d"),
            "end": end.strftime("%Y-%m-%d"),
            "rainfall_anomaly_pct": round(r, 1) if math.isfinite(r) else None,
            "ndvi_anomaly_pct":     round(v, 1) if math.isfinite(v) else None,
            "compound_severity": score_severity(r, v),  # OK, r y v ya son diferencias %
            "evidence": f"r3q medio {r:+.1f} %, viq medio {v:+.1f} %"  # OK
        })
    return out


def compute_worst_period(df: pd.DataFrame, window_months: int = 12) -> dict | None:
    """
    Ventana móvil de `window_months` meses con menor score compuesto.
    Solo reporta si hubo un déficit real (score < 0).
    Devuelve None si no hay datos suficientes o si nunca hubo déficit.
    """
    sub = df.dropna(subset=["r3q", "viq"]).copy()
    if len(sub) < 30:
        return None

    sub = sub.sort_values("date").reset_index(drop=True)

    best = None
    end_max = sub["date"].max()
    start_min = sub["date"].min()

    cur_start = start_min
    while True:
        cur_end = cur_start + pd.DateOffset(months=window_months)
        if cur_end > end_max:
            break
        win = sub[(sub["date"] >= cur_start) & (sub["date"] < cur_end)]
        if len(win) >= 20:
            r = float(win["r3q"].mean()) - 100.0
            v = float(win["viq"].mean()) - 100.0
            score = 0.6 * r + 0.4 * v
            if best is None or score < best["score"]:
                best = {
                    "start": cur_start.strftime("%Y-%m-%d"),
                    "end": cur_end.strftime("%Y-%m-%d"),
                    "r": r,
                    "v": v,
                    "score": score,
                }
        cur_start = cur_start + pd.Timedelta(days=10)

    # Solo reportar si hubo un déficit real (score compuesto negativo).
    if best is None or best["score"] >= 0:
        return None

    severity = score_severity(best["r"], best["v"])
    return {
        "start": best["start"],
        "end": best["end"],
        "rainfall_anomaly_pct": round(best["r"], 1),
        "ndvi_anomaly_pct":     round(best["v"], 1),
        "compound_severity":    severity,
        "explanation": (
            f"Entre {best['start'][:7]} y {best['end'][:7]}, la lluvia acumulada "
            f"estuvo {best['r']:+.1f} % y el NDVI {best['v']:+.1f} % respecto al "
            f"promedio histórico, configurando una sequía compuesta de severidad "
            f"{severity}."
        ),
    }

def compute_climatology_36(df: pd.DataFrame) -> tuple[list[dict] | None, list[dict] | None]:
    """
    Devuelve (rain_clima, ndvi_clima) agregados por dekad-of-year (1..36).
    Usa r3h_avg y vim_lta del backend. Si no están, devuelve (None, None).
    """
    if df["r3h_avg"].isna().all() or df["vim_lta"].isna().all():
        return None, None

    df = df.copy()
    df["doy"] = df["date"].dt.dayofyear
    # dekad-of-year: 1..36 (0-based → +1). floor(doy / 10) da 0..36.
    df["dekad"] = (df["doy"] // 10).clip(0, 35) + 1

    rain_clima = (
        df.groupby("dekad")["r3h_avg"].mean().dropna()
        .reset_index().sort_values("dekad")
    )
    ndvi_clima = (
        df.groupby("dekad")["vim_lta"].mean().dropna()
        .reset_index().sort_values("dekad")
    )

    r = [{"dekad": int(r.dekad), "lta": round(float(r.r3h_avg), 3)}
         for r in rain_clima.itertuples()]
    n = [{"dekad": int(r.dekad), "lta": round(float(r.vim_lta), 4)}
         for r in ndvi_clima.itertuples()]
    return r, n