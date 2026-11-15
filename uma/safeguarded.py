"""Evaluación conservadora de anomalías y evidencia de presión humana."""
from __future__ import annotations
import numpy as np
import pandas as pd
from . import validation

_CACHE = {}

def climate(df, baseline_end):
    # La caché identifica TODOS los datos de entrada y el corte; no comparte ajustes entre lagos.
    cfg = validation.policy()
    key = (baseline_end, pd.util.hash_pandas_object(df, index=True).values.tobytes(), str(cfg))
    if key not in _CACHE:
        _CACHE[key] = validation.fit_selected(df, baseline_end, cfg)
    return _CACHE[key]

def audit_suspects(df, resid, sus, resid_break, baseline_end):
    from .engine import base_name, pettitt, holm, suspect_label, CONTEXT_ONLY
    out = []
    for name, g in sus.groupby("suspect"):
        if base_name(name) in CONTEXT_ONLY:
            continue
        if g.year.duplicated().any(): raise ValueError(f"Presión duplicada: {name}")
        s = g.set_index("year").value.reindex(df.index).astype(float)
        # No convertir falta de información en ausencia de presión.
        flagged = "value_status" in g and g.value_status.notna().any()
        if flagged:
            status = g.set_index("year").value_status.reindex(df.index)
            s = s.where(status.isna() | status.isin(["observed", "zero_within_product_coverage"]))
        valid = s.dropna()
        if len(valid) < 12 or valid.std() < 1e-10: continue
        trend = validation.block_trend(valid)
        idx, cp_p = pettitt(valid.to_numpy())
        onset = int(valid.index[idx]) if cp_p < .1 else None
        rho, p, n = validation.negative_association(s, resid)
        precedes = onset is not None and resid_break is not None and 0 <= resid_break - onset <= 5
        out.append({"suspect": name, "label": suspect_label(name), "onset": onset,
                    "rho": rho, "p": p, "trend_p": trend["p"], "r2": rho*rho,
                    "precedes": bool(precedes), "rising": trend["tau"] > 0 and trend["p"] < .05,
                    "paired_changes": n, "observed_years": len(valid),
                    "data_provenance": "flagged" if flagged else "legacy_unverified",
                    "together_with": []})
    adjusted = holm({r["suspect"]: r["p"] for r in out})
    trend_adjusted = holm({r["suspect"]: r["trend_p"] for r in out})
    for r in out:
        r["p_adjusted"] = adjusted[r["suspect"]]
        r["trend_p_adjusted"] = trend_adjusted[r["suspect"]]
        r["eligible"] = bool(r["rho"] < 0 and r["p_adjusted"] < .05 and r["trend_p_adjusted"] < .05 and r["rising"] and r["precedes"])
        r["evidence"] = "consistente" if r["eligible"] else "exploratoria"
        r["score"] = int(r["eligible"]) * 10 + int(r["precedes"]) + max(0, -r["rho"])
    return sorted(out, key=lambda r: r["score"], reverse=True)

def finalize(r):
    r["n_pass"] = sum(t["pass"] for t in r["tests"].values())
    if not r["quality"]["eligible"] or not r["model_validation"]["reliable"]:
        state, confidence = "Evidencia insuficiente", "No evaluable"
    elif not r["tests"]["clima"]["pass"]:
        state, confidence = "Sin perdida anomala detectada", "Limitada"
    elif r["model_validation"].get("climate_attribution_eligible", False) and r["tests"]["control"]["pass"] and r["tests"]["coincidencia"]["pass"]:
        state = "Evidencia reforzada de intervencion" if r["independent_evidence"] else "Indicios de intervencion humana"
        confidence = "Reforzada" if r["independent_evidence"] else "Exploratoria"
    else:
        state, confidence = "Perdida no explicada", "Limitada"
    r["state"], r["confidence"] = state, confidence
    return r


def adjust_evidence(results):
    from .engine import ALPHA, holm
    for name in ("clima", "control"):
        corrected = holm({r["body_id"]: r["tests"][name]["p"] for r in results
                          if r["tests"][name].get("evaluated") and r["tests"][name].get("p") is not None})
        for result in results:
            test = result["tests"][name]
            test["p_adjusted"] = corrected.get(result["body_id"])
            test["pass"] = bool(test["pass"] and test["p_adjusted"] is not None and test["p_adjusted"] < ALPHA)
            if test["p_adjusted"] is not None:
                test["detail"] += f" Holm entre cuerpos: p={test['p_adjusted']:.3f}."
    return [finalize(result) for result in results]


def analyze_body(body_id, series, suspects, control_id, baseline_end):
    from .engine import sen_slope, mann_kendall, pettitt
    cfg = validation.policy()
    full = validation.prepare(series.loc[series.body_id.eq(body_id)])
    df = full.loc[full[validation.FEATURES].notna().all(axis=1)].copy()
    if df.empty:
        raise ValueError(f"{body_id}: sin años con clima utilizable.")
    result = climate(df, baseline_end)
    fit = result["expected"]
    observed = df.water_ha.where(~df.water_imputed)
    resid = observed - fit
    valid = resid.dropna()
    trend = mann_kendall(observed)
    span = int(df.index[-1] - df.index[0])
    base = observed.loc[:baseline_end].dropna()
    base_mean = float(base.mean())
    loss_pct = 100 * sen_slope(valid.index, valid) * span / max(base_mean, 1e-8)
    rt = validation.block_trend(valid)
    below = (observed < result["lower"]) & (df.index > baseline_end)
    longest = run = 0
    for value in below:
        run = run + 1 if value else 0
        longest = max(longest, run)
    t1 = rt["tau"] < 0 and rt["p"] < .05 and loss_pct <= -cfg["min_effect_pct"] and longest >= cfg["consecutive_low_years"]
    tests = {"clima": {"pass": bool(t1), "p": rt["p"], "evaluated": True,
        "detail": f"Residuo {loss_pct:+.1f}% de la media base; p por bloques={rt['p']:.3f}; {longest} años consecutivos bajo la banda. No identifica causa."},
        "control": {"pass": False, "p": None, "evaluated": False, "detail": "No hay control elegible documentado."}}
    control_eval = {"eligible": False, "reasons": ["Sin control asignado."]}
    if control_id and series.body_id.eq(control_id).any():
        control = validation.prepare(series.loc[series.body_id.eq(control_id)])
        control = control.loc[control[validation.FEATURES].notna().all(axis=1)]
        cr = climate(control, baseline_end)
        control_eval = validation.control_assessment(df, control, cr, control_id, baseline_end, cfg)
        cres = control.water_ha.where(~control.water_imputed) - cr["expected"]
        cm = float(control.water_ha.where(~control.water_imputed).loc[:baseline_end].mean())
        diff = (resid / max(base_mean, 1e-8) - cres / max(cm, 1e-8)).dropna()
        stat = validation.block_trend(diff)
        tests["control"] = {"pass": bool(control_eval["eligible"] and stat["tau"] < 0 and stat["p"] < .05),
            "p": stat["p"] if control_eval["eligible"] else None, "evaluated": control_eval["eligible"],
            "detail": f"Control {control_id}: " + ("elegible; p por bloques=" + str(round(stat["p"], 3)) if control_eval["eligible"] else "; ".join(control_eval["reasons"]))}
    idx, cp_p = pettitt(valid.to_numpy())
    break_year = int(valid.index[idx]) if cp_p < .1 else None
    ranked = audit_suspects(df, resid, suspects.loc[suspects.body_id.eq(body_id)], break_year, baseline_end)
    top = ranked[0] if ranked else None
    tests["coincidencia"] = {"pass": bool(top and top["eligible"]), "p": top["p_adjusted"] if top else None,
        "evaluated": bool(ranked), "detail": "Exige presión creciente, antecedencia 0–5 años, asociación NEGATIVA de cambios anuales y p corregidos por Holm. No prueba causalidad."}
    imputed_fraction = float(full.water_imputed.mean())
    quality = {"eligible": bool(imputed_fraction <= cfg["max_imputed_fraction"] and len(base) >= cfg["min_baseline_observed"]),
        "input_n": len(full), "analyzed_n": len(df), "base_observed_n": len(base),
        "imputed_water_n": int(full.water_imputed.sum()), "imputed_fraction": imputed_fraction,
        "legacy_quality": "Se infieren imputaciones por nodata_pct > 20; otras imputaciones históricas pueden no estar marcadas.",
        "reasons": []}
    if imputed_fraction > cfg["max_imputed_fraction"]: quality["reasons"].append("Demasiados años de agua imputada.")
    if len(base) < cfg["min_baseline_observed"]: quality["reasons"].append("Pocas observaciones base utilizables.")
    evidence = [e for e in cfg["documented_interventions"] if e.get("body_id") == body_id and top and e.get("suspect") == top["suspect"]
                and e.get("reviewed") is True and e.get("human_activity_verified") is True and e.get("source")
                and isinstance(e.get("year"), int) and break_year is not None and 0 <= break_year-e["year"] <= 5]
    total_change = sen_slope(df.index, observed) * span
    climate_change = sen_slope(df.index, fit) * span
    r = {"body_id": body_id, "years": [int(y) for y in df.index],
         "observed": [None if pd.isna(v) else round(float(v), 2) for v in observed],
         "observed_imputed": [bool(v) for v in df.water_imputed],
         "expected": [round(float(v), 2) for v in fit],
         "expected_lower": result["lower"].round(2).tolist(), "expected_upper": result["upper"].round(2).tolist(),
         "oni": df.oni.round(2).tolist(), "baseline_end": baseline_end, "baseline_mean_ha": base_mean,
         "trend": {**trend, "sen_ha_per_year": sen_slope(df.index, observed),
                   "change_pct": float(100 * (observed.iloc[-5:].mean() - base_mean) / max(base_mean, 1e-8))},
         "climate_r2": result["r2"], "selected_model": result["selected"], "model_comparison": result["metrics"],
         "model_validation": {"reliable": result["reliable"], "base_n": result["base_n"], "cv_n": result["cv_n"],
                              "climate_attribution_eligible": result["reliable"] and result["selected"] != "climatologia",
                              "cv_skill_vs_climatology": result["cv_skill"], "selection": "solo período base",
                              "interval_method": "bootstrap aproximado de residuos en bloques; NO calibración garantizada"},
         "interval_level": result["interval_level"], "tests": tests, "quality": quality, "control_validation": control_eval,
         "independent_evidence": evidence, "residual_break": break_year,
         "decomposition_ha": {"Cambio esperado por modelo": round(climate_change, 1), "Diferencia de tendencias no atribuida": round(total_change - climate_change, 1)},
         "suspects": ranked, "backtest": result["backtest"], "method_version": "2-conservador"}
    return finalize(r)
