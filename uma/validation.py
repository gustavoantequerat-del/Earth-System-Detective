"""Comparación temporal, incertidumbre y calidad del modelo climático.

La selección usa SOLO observaciones anteriores al final del período base.
Los intervalos bootstrap son aproximados; se publica su cobertura posterior.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

FEATURES = ["precip_mm", "precip_lag1", "temp_c", "oni"]
METHODS = ["climatologia", "ols", "ridge", "dinamico_ar1"]

def policy():
    return json.loads((Path(__file__).resolve().parent.parent / "config/evidence_policy.json").read_text(encoding="utf-8"))

def prepare(df):
    df = df.sort_values("year").copy()
    if df.year.duplicated().any():
        raise ValueError("Años duplicados dentro de un cuerpo de agua.")
    if len(df) and not np.array_equal(df.year.to_numpy(), np.arange(df.year.min(), df.year.max() + 1)):
        raise ValueError("Hay huecos anuales; no se desplaza lluvia entre años no consecutivos.")
    known = "nodata_pct" in df.columns or "water_imputed" in df.columns
    explicit = df.get("water_imputed", pd.Series(False, index=df.index)).fillna(True)
    if explicit.dtype == object:
        explicit = explicit.astype(str).str.lower().isin(["true", "1", "yes"])
    df["water_imputed"] = explicit | df.get("nodata_pct", pd.Series(0., index=df.index)).gt(20) | df.water_ha.isna()
    df["water_quality_known"] = known
    df["precip_lag1"] = df.precip_mm.shift(1)  # primera observación queda ausente, sin bfill
    return df.set_index("year")

def _fit(method, X, y, years=None):
    mean, scale = X.mean(axis=0), X.std(axis=0)
    scale = np.where(scale > 1e-8, scale, 1.)
    Z = np.column_stack([np.ones(len(X)), (X - mean) / scale])
    if method == "climatologia":
        beta = np.r_[y.mean(), np.zeros(X.shape[1])]
    elif method == "ridge":
        penalty = np.diag([0.] + [1.] * X.shape[1])
        beta = np.linalg.solve(Z.T @ Z + penalty, Z.T @ y)
    else:
        beta = np.linalg.lstsq(Z, y, rcond=None)[0]
    fitted = Z @ beta
    residual = y - fitted
    phi = 0.
    if method == "dinamico_ar1" and len(y) > 2:
        pairs = np.ones(len(y)-1, dtype=bool) if years is None else np.diff(np.asarray(years)) == 1
        previous, following = residual[:-1][pairs], residual[1:][pairs]
        den = previous @ previous
        phi = float(np.clip((previous @ following) / den, -.95, .95)) if den > 1e-8 else 0.
    return {"beta": beta, "mean": mean, "scale": scale, "phi": phi, "last_resid": float(residual[-1]), "fitted": fitted}

def _predict(model, X, horizons=None):
    pred = np.column_stack([np.ones(len(X)), (X - model["mean"]) / model["scale"]]) @ model["beta"]
    if horizons is not None and model["phi"] != 0:
        pred += np.where(horizons > 0, model["last_resid"] * np.power(model["phi"], horizons), 0.)
    return np.maximum(0., pred)

def _blocks(rng, values, size, block):
    block = min(block, len(values))
    starts = rng.integers(0, len(values) - block + 1, size=int(np.ceil(size / block)))
    return np.concatenate([values[i:i + block] for i in starts])[:size]

def fit_selected(df, baseline_end, settings=None):
    cfg = settings or policy()
    good_x = df[FEATURES].notna().all(axis=1)
    base = df.loc[(df.index <= baseline_end) & good_x & ~df.water_imputed & df.water_ha.notna()]
    if not len(base):
        raise ValueError("No hay observaciones base utilizables; revisar los datos y el corte.")
    methods = METHODS if len(base) >= 8 else ["climatologia"]
    X, y = base[FEATURES].to_numpy(float), base.water_ha.to_numpy(float)
    cv = {m: [] for m in methods}
    for cut in range(10, len(base), 2):
        ix = slice(cut, min(cut + 2, len(base)))
        horizons = base.index.to_numpy()[ix] - base.index[cut-1]
        for method in methods:
            model = _fit(method, X[:cut], y[:cut], base.index.to_numpy()[:cut])
            predictions = _predict(model, X[ix], horizons)
            cv[method].extend((y[ix] - predictions).tolist())
    scores = {m: float(np.mean(np.abs(e))) if e else None for m, e in cv.items()}
    selected = min(methods, key=lambda m: scores[m] if scores[m] is not None else np.inf)
    model = _fit(selected, X, y, base.index.to_numpy())
    all_x = df.loc[good_x, FEATURES].to_numpy(float)
    years = df.index[good_x].to_numpy()
    horizons = np.maximum(0, years - base.index[-1])
    expected = pd.Series(np.nan, index=df.index, dtype=float)
    expected.loc[good_x] = _predict(model, all_x, horizons)
    # Bootstrap de residuos base en bloques: incertidumbre de ajuste más variación de nuevas observaciones.
    # No se usan valores water_ha posteriores al corte, ni para selección ni para bandas.
    residual = y - model["fitted"]
    residual -= residual.mean()
    rng = np.random.default_rng(20261114)
    draws = []
    for _ in range(int(cfg["bootstrap_draws"])):
        pseudo = model["fitted"] + _blocks(rng, residual, len(y), cfg["block_length"])
        boot = _fit(selected, X, pseudo, base.index.to_numpy())
        prediction = _predict(boot, all_x, horizons)
        prediction += _blocks(rng, residual, len(all_x), cfg["block_length"])
        draws.append(np.maximum(0, prediction))
    q = (1 - cfg["interval_level"]) / 2
    low, high = np.quantile(draws, [q, 1-q], axis=0)
    lower, upper = expected.copy(), expected.copy()
    lower.loc[good_x], upper.loc[good_x] = low, high
    den = np.sum((y - y.mean())**2)
    r2 = 1 - np.sum((y - model["fitted"])**2) / den if den > 0 else 0.
    normalizer = max(abs(float(y.mean())), 1e-8)
    metrics = []
    target = df.loc[(df.index > baseline_end) & good_x & ~df.water_imputed & df.water_ha.notna()]
    for method in methods:
        candidate = _fit(method, X, y, base.index.to_numpy())
        pred = _predict(candidate, target[FEATURES].to_numpy(float), target.index.to_numpy() - base.index[-1])
        error = target.water_ha.to_numpy() - pred
        metrics.append({"method": method, "cv_mae_ha": scores[method], "cv_n": len(cv[method]),
                        "mae_ha": float(np.mean(abs(error))) if len(error) else None,
                        "rmse_ha": float(np.sqrt(np.mean(error**2))) if len(error) else None,
                        "bias_ha": float(np.mean(error)) if len(error) else None,
                        "selected": method == selected, "test_n": len(error)})
    err = target.water_ha - expected.loc[target.index]
    coverage = float(target.water_ha.between(lower.loc[target.index], upper.loc[target.index]).mean()) if len(target) else None
    selected_mae = scores[selected]
    reference_mae = scores["climatologia"]
    skill = 1 - selected_mae / reference_mae if reference_mae and selected_mae is not None else 0.
    reliable = len(base) >= cfg["min_baseline_observed"] and len(cv[selected]) >= cfg["min_cv_predictions"] and skill >= -1e-8
    coefficients = pd.Series(model["beta"][1:] / model["scale"], index=FEATURES)
    contributions = {v: coefficients[v] * (df[v] - base[v].mean()) for v in FEATURES}
    return {"expected": expected, "lower": lower, "upper": upper, "r2": float(r2),
            "contributions": contributions, "selected": selected, "metrics": metrics,
            "base_n": len(base), "cv_n": len(cv[selected]), "cv_skill": float(skill), "reliable": bool(reliable),
            "interval_level": cfg["interval_level"], "coverage": coverage,
            "backtest": {"mae_ha": float(err.abs().mean()) if len(err) else None,
                         "rmse_ha": float(np.sqrt((err**2).mean())) if len(err) else None,
                         "bias_ha": float(err.mean()) if len(err) else None,
                         "mae_pct": float(100 * err.abs().mean() / normalizer) if len(err) else None,
                         "normalization": "media del agua observada utilizable en entrenamiento",
                         "coverage": coverage, "interval_level": cfg["interval_level"], "n": len(target)}}

def block_trend(y, block=3, repetitions=499):
    """p exploratorio por permutación de bloques, preserva dependencia dentro de cada bloque."""
    if isinstance(y, pd.Series):
        s = y.sort_index().dropna()
        groups = s.groupby(s.index.to_series().diff().ne(1).cumsum())
        chunks = [g.to_numpy(float)[i:i+block] for _, g in groups for i in range(0, len(g), block)]
        y = s.to_numpy(float)
    else:
        y = np.asarray(y, float); y = y[np.isfinite(y)]
        chunks = [y[i:i+block] for i in range(0, len(y), block)]
    if len(y) < 8 or np.std(y) < 1e-10:
        return {"tau": 0., "p": 1.}
    t = np.arange(len(y)); tau = float(stats.kendalltau(t, y).statistic)
    rng = np.random.default_rng(71)
    null = [stats.kendalltau(t, np.concatenate([chunks[i] for i in rng.permutation(len(chunks))])).statistic for _ in range(repetitions)]
    return {"tau": tau, "p": float((1 + np.sum(np.abs(null) >= abs(tau))) / (repetitions + 1))}

def negative_association(x, y):
    """Spearman sobre cambios anuales; p por desplazamientos circulares de una serie.

    Exploratorio, no prueba causal. Se exige continuidad y un mínimo de 12 cambios emparejados.
    """
    z = pd.concat([x.rename("x"), y.rename("y")], axis=1).sort_index()
    dx, dy = z.x.diff(), z.y.diff()
    dx.loc[z.index.to_series().diff().ne(1)] = np.nan
    ok = dx.notna() & dy.notna()
    a, b = dx[ok].to_numpy(), dy[ok].to_numpy()
    if len(a) < 12 or np.std(a) < 1e-10 or np.std(b) < 1e-10:
        return 0., 1., len(a)
    rho = float(stats.spearmanr(a, b).statistic)
    null = [stats.spearmanr(np.roll(a, k), b).statistic for k in range(1, len(a))]
    p = float((1 + np.sum(np.abs(null) >= abs(rho))) / len(a))
    return rho, p, len(a)

def control_assessment(target, control, control_fit, control_id, baseline_end, cfg):
    review = cfg["control_reviews"].get(control_id, {})
    approved = review.get("approved") is True and bool(review.get("source")) and bool(review.get("reviewer"))
    pre = pd.concat([target.water_ha.where(~target.water_imputed).rename("a"), control.water_ha.where(~control.water_imputed).rename("b")], axis=1).loc[:baseline_end].dropna()
    corr = float(pre.a.corr(pre.b)) if len(pre) >= 8 and pre.a.std() and pre.b.std() else None
    metrics = control_fit["backtest"]
    reasons = []
    if not approved: reasons.append("Control candidato sin revision independiente documentada.")
    if corr is None or corr < cfg["min_pre_control_correlation"]: reasons.append("Similitud previa insuficiente.")
    if not control_fit["reliable"]: reasons.append("Validacion temporal base insuficiente en control.")
    if metrics["mae_pct"] is None or metrics["mae_pct"] > cfg["max_control_mae_baseline_pct"]: reasons.append("Error posterior elevado en control.")
    if metrics["coverage"] is None or metrics["coverage"] < cfg["min_control_coverage"]: reasons.append("Baja cobertura posterior en control.")
    return {"eligible": not reasons, "reviewed": bool(approved), "pre_correlation": corr,
            "mae_baseline_pct": metrics["mae_pct"], "coverage": metrics["coverage"], "reasons": reasons}
