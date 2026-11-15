"""Modelo de clima y pruebas con datos mensuales (data/real/monthly.csv).

Por que: la serie anual tiene 16 anos en el periodo base; la mensual tiene hasta 192 meses. Pero los meses
seguidos se parecen entre si (autocorrelacion), asi que contarlos como datos independientes inflaria la
confianza. Por eso:
- el modelo de clima usa errores robustos de Newey-West (HAC, 12 rezagos);
- las tendencias usan Mann-Kendall modificado de Hamed y Rao (1998), que corrige la varianza por la
  autocorrelacion de los rangos.

Se trabaja con anomalias: a cada mes se le resta su promedio del periodo base (asi la estacion de lluvias no
cuenta como tendencia) y se expresan como fraccion del agua media del periodo base, para poder pasarlas a la
serie anual de Landsat, que mide en otra escala.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

WINDOWS = (6, 12, 24, 36)   # meses acumulados de lluvia menos evaporacion (memoria del lago); se elige por AIC
HAC_LAGS = 12
MIN_MONTHS_BASE = 36        # meses con agua observada en el periodo base para fitear


def modified_mk(y) -> dict:
    """Mann-Kendall con correccion de Hamed y Rao (1998) por autocorrelacion."""
    y = np.asarray(y, dtype=float)
    y = y[~np.isnan(y)]
    n = len(y)
    if n < 10:
        return {"tau": 0.0, "z": 0.0, "p": 1.0, "n": n, "n_eff": n}
    s = sum(np.sign(y[i + 1:] - y[i]).sum() for i in range(n - 1))
    _, counts = np.unique(y, return_counts=True)
    var_s = (n * (n - 1) * (2 * n + 5) - (counts * (counts - 1) * (2 * counts + 5)).sum()) / 18.0
    # autocorrelacion de los rangos de la serie sin tendencia (pendiente de Sen)
    x = np.arange(n)
    slope = stats.theilslopes(y, x)[0]
    r = stats.rankdata(y - slope * x)
    r = r - r.mean()
    denom = (r ** 2).sum()
    corr = 0.0
    bound = 1.96 / math.sqrt(n)
    for k in range(1, n - 1):
        rho = (r[:-k] * r[k:]).sum() / denom
        if abs(rho) > bound:
            corr += (n - k) * (n - k - 1) * (n - k - 2) * rho
    factor = max(1 + 2 / (n * (n - 1) * (n - 2)) * corr, 1.0)
    var_s *= factor
    z = (s - np.sign(s)) / math.sqrt(var_s) if s != 0 else 0.0
    tau = s / (0.5 * n * (n - 1))
    return {"tau": float(tau), "z": float(z), "p": float(2 * (1 - stats.norm.cdf(abs(z)))), "n": n,
            "n_eff": round(n / factor)}


def _z(x: pd.Series) -> pd.Series:
    sd = x.std()
    return (x - x.mean()) / sd if sd and sd > 0 else x * 0


def prep(m: pd.DataFrame, baseline_end: int, upstream_annual: pd.Series | None = None) -> pd.DataFrame | None:
    """Anomalias mensuales relativas y predictores del clima."""
    d = m.sort_values(["year", "month"]).copy()
    d["t"] = d.year + (d.month - 0.5) / 12
    base = d[d.year <= baseline_end]
    if base.water_ha.notna().sum() < MIN_MONTHS_BASE:
        return None
    clim = base.groupby("month").water_ha.mean()
    level = float(base.water_ha.mean())
    if not level:
        return None
    d["anom"] = (d.water_ha - d.month.map(clim)) / level
    pet = "pet_lake_mm" if "pet_lake_mm" in d and d["pet_lake_mm"].notna().sum() > 100 else "pet_mm"
    for v in ("precip_mm", pet):
        d[v] = d[v].interpolate(limit_direction="both")
        d[v + "_a"] = d[v] - d.month.map(base.groupby("month")[v].mean())
    wb = _z(d["precip_mm_a"]) - _z(d[pet + "_a"])
    for w in WINDOWS:
        d[f"wb{w}"] = wb.rolling(w, min_periods=w // 2).sum()
    d["oni"] = d["oni"].interpolate(limit_direction="both")
    if upstream_annual is not None:
        up = upstream_annual.reindex(d.year.unique()).interpolate(limit_direction="both")
        d["upstream"] = _z(d.year.map(up))
    d.attrs["level"] = level
    return d.reset_index(drop=True)


@dataclass
class MonthlyFit:
    reliable: bool
    window: int
    expected: pd.Series          # anomalia relativa esperada por el clima, todos los meses
    contributions: dict          # por variable
    info: dict


def fit(d: pd.DataFrame, baseline_end: int, use_upstream: bool = False) -> MonthlyFit:
    base = d[(d.year <= baseline_end)].dropna(subset=["anom"])
    best = None
    for w in WINDOWS:
        cols = [f"wb{w}", "oni"] + (["upstream"] if use_upstream else [])
        b = base.dropna(subset=cols)
        if len(b) < MIN_MONTHS_BASE:
            continue
        mdl = sm.OLS(b["anom"], sm.add_constant(b[cols])).fit(cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS})
        if best is None or mdl.aic < best[1].aic:
            best = (w, mdl, cols)
    if best is None:
        return MonthlyFit(False, 0, pd.Series(0.0, index=d.index), {}, {"motivo": "pocos meses observados"})
    w, mdl, cols = best
    key = "upstream" if use_upstream else f"wb{w}"
    f_p = float(mdl.f_pvalue)
    reliable = bool(f_p < 0.05 and mdl.params[key] > 0 and mdl.pvalues[key] < 0.10)
    X = sm.add_constant(d[cols].ffill().bfill(), has_constant="add")
    means = base[cols].mean()
    contrib = {c: mdl.params[c] * (d[c].ffill().bfill() - means[c]) for c in cols}
    info = {"ventana_meses": w, "r2": round(float(mdl.rsquared), 3), "f_p_hac": f_p, "n_base": int(mdl.nobs),
            "coef": float(mdl.params[key]), "p_coef_hac": float(mdl.pvalues[key])}
    return MonthlyFit(reliable, w, mdl.predict(X) if reliable else pd.Series(0.0, index=d.index),
                      contrib if reliable else {c: pd.Series(0.0, index=d.index) for c in cols}, info)


def residual_trend(d: pd.DataFrame, mf: MonthlyFit) -> dict:
    """Tendencia de lo que el clima no explica, mes a mes, con Mann-Kendall corregido."""
    r = (d["anom"] - mf.expected).where(d["anom"].notna())
    ok = r.dropna()
    mk = modified_mk(ok.values)
    slope = stats.theilslopes(ok.values, d.loc[ok.index, "t"].values)[0] if len(ok) > 10 else 0.0
    span = float(d.loc[ok.index, "t"].max() - d.loc[ok.index, "t"].min()) if len(ok) else 0.0
    return {**mk, "pct": 100 * slope * span, "series": r}


def twin_trend(d: pd.DataFrame, mf: MonthlyFit, dc: pd.DataFrame, mfc: MonthlyFit) -> dict:
    r = (d["anom"] - mf.expected).where(d["anom"].notna())
    rc = (dc["anom"] - mfc.expected).where(dc["anom"].notna())
    a = pd.Series(r.values, index=d.t.round(3)).dropna()
    b = pd.Series(rc.values, index=dc.t.round(3)).dropna()
    diff = (a - b).dropna()
    mk = modified_mk(diff.values)
    slope = stats.theilslopes(diff.values, diff.index.values)[0] if len(diff) > 10 else 0.0
    span = float(diff.index.max() - diff.index.min()) if len(diff) else 0.0
    return {**mk, "pct": 100 * slope * span}


def annual(d: pd.DataFrame, s: pd.Series) -> pd.Series:
    """Promedio anual de una serie mensual (anomalia relativa)."""
    return s.groupby(d.year).mean()
