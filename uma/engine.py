"""Motor de atribucion de Uma.

Separa la huella humana del clima en la serie de agua de un cuerpo de agua.
Siempre los mismos pasos:
  1. Tendencia (Mann-Kendall + pendiente de Sen)
  2. Prueba 1: lo que explica el clima (modelo entrenado en el periodo base)
  3. Prueba 2: comparacion con la gemela de control
  4. Prueba 3: coincidencia en el tiempo con un sospechoso
  5. Descomposicion, confianza, auditoria de sospechosos y estado

Formato de entrada (contrato con P1, ver README):
  bodies.csv   body_id, name, lat, lon, kind, control_id, department
  series.csv   body_id, year, water_ha, precip_mm, temp_c, oni
  suspects.csv body_id, year, suspect, value
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

ALPHA = 0.05
# El modelo de clima usa el balance de agua de dos anos (anomalia de lluvia menos anomalia de evaporacion
# potencial, este ano y el anterior) y El Nino: dos variables con sentido fisico en lugar de cuatro, porque
# el periodo base tiene solo 16 anos. Se usan anomalias estandarizadas porque la evaporacion de ERA5-Land
# esta sesgada en los llanos (valores de 5000-6000 mm) y asi el sesgo del promedio no pesa.
CLIMATE_VARS = ["water_balance", "oni"]
CLIMATE_GROUPS = {"Lluvia menos evaporacion": ["water_balance"], "El Nino": ["oni"]}
CLIMATE_P_MAX = 0.05     # el modelo de clima debe ser significativo (prueba F)
STATE_UNKNOWN = "Incalculable"
TWIN_MAX_CHANGE = 25    # una gemela que cambio mas del 25% no sirve de referencia
SMALL_EFFECT_PCT = 15   # perdidas de 10-15%: veredicto fragil, confianza baja
MAX_LAG_YEARS = 5
MIN_EFFECT_PCT = 10  # una perdida menor al 10% de la media base no se considera relevante
CLIMATE_SHARE_MIN = 0.6  # para decir "causa climatica", el clima debe explicar al menos el 60% de la perdida

SUSPECT_LABELS = {
    "forest_loss_ha": "Desmonte",
    "burned_ha": "Incendios",
    "dry_crop_ha": "Agricultura con riego",
    "pasture_ha": "Ganaderia",
    "mining_ha": "Mineria",
    "urban_ha": "Crecimiento urbano",
    "artificial_water_ha": "Represas y reservorios",
    "mining_water_ha": "Pozas mineras",
    "human_land_ha": "Uso humano del suelo (5 km)",
    "agri_ha": "Agricultura",
    "night_lights": "Luces nocturnas (ciudad e industria)",
    "population": "Poblacion",
    "crop_water_hm3": "Agua consumida por cultivos",
    "desaguadero_deficit_idx": "Menos agua por el Desaguadero (posible desvio)",
}


# ---------------------------------------------------------------- estadistica
def mann_kendall(y) -> dict:
    """Mann-Kendall con correccion por empates. Devuelve tau, z, p."""
    y = np.asarray(y, dtype=float)
    y = y[~np.isnan(y)]
    n = len(y)
    if n < 4:
        return {"tau": 0.0, "z": 0.0, "p": 1.0}
    s = 0.0
    for i in range(n - 1):
        s += np.sign(y[i + 1:] - y[i]).sum()
    _, counts = np.unique(y, return_counts=True)
    var_s = (n * (n - 1) * (2 * n + 5) - (counts * (counts - 1) * (2 * counts + 5)).sum()) / 18.0
    if var_s <= 0:
        return {"tau": 0.0, "z": 0.0, "p": 1.0}
    z = (s - np.sign(s)) / math.sqrt(var_s) if s != 0 else 0.0
    p = 2 * (1 - stats.norm.cdf(abs(z)))
    tau = s / (0.5 * n * (n - 1))
    return {"tau": float(tau), "z": float(z), "p": float(p)}


def sen_slope(x, y) -> float:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = ~np.isnan(y)
    x, y = x[ok], y[ok]
    slopes = [(y[j] - y[i]) / (x[j] - x[i]) for i in range(len(x)) for j in range(i + 1, len(x)) if x[j] != x[i]]
    return float(np.median(slopes)) if slopes else 0.0


def pettitt(y) -> tuple[int, float]:
    """Prueba de Pettitt: indice del punto de cambio y su valor p aproximado."""
    y = np.asarray(y, dtype=float)
    n = len(y)
    if n < 6:
        return 0, 1.0
    u = np.array([np.sign(y[: t + 1, None] - y[None, t + 1:]).sum() for t in range(n - 1)])
    k = int(np.argmax(np.abs(u)))
    kmax = abs(u[k])
    p = min(1.0, 2 * math.exp(-6 * kmax**2 / (n**3 + n**2)))
    return k + 1, float(p)  # primer indice del segundo tramo


def holm(pvalues: dict[str, float]) -> dict[str, float]:
    """Correccion de Holm para pruebas multiples (muchos cuerpos de agua)."""
    items = sorted(pvalues.items(), key=lambda kv: kv[1])
    m = len(items)
    out, running = {}, 0.0
    for i, (k, p) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        out[k] = running
    return out


# ---------------------------------------------------------------- modelo
@dataclass
class ClimateFit:
    model: object
    baseline_end: int
    r2: float
    expected: pd.Series
    contributions: dict[str, pd.Series]
    reliable: bool = False
    info: dict | None = None


def _z(x: pd.Series) -> pd.Series:
    sd = x.std()
    return (x - x.mean()) / sd if sd and sd > 0 else x * 0


def _prep(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("year").copy()
    df["precip_lag1"] = df["precip_mm"].shift(1).bfill()
    if "pet_mm" in df and df["pet_mm"].notna().sum() > 10:
        wb = _z(df["precip_mm"]) - _z(df["pet_mm"].interpolate(limit_direction="both"))
    else:  # sin evaporacion potencial: solo lluvia
        wb = _z(df["precip_mm"])
    df["water_balance"] = wb + wb.shift(1).bfill()
    return df.set_index("year")


def fit_climate(df: pd.DataFrame, baseline_end: int) -> ClimateFit:
    """Ajusta agua ~ balance de agua (2 anos) + ONI solo en el periodo base.

    Entrenar solo en el periodo base evita que el modelo de clima absorba la tendencia humana posterior.
    El modelo es confiable si es significativo (p < 0.05) y si mas balance de agua da mas agua (efecto
    positivo, p < 0.10). Si no lo es, no se usa para atribuir: el agua esperada queda en el promedio base.
    """
    base = df.loc[:baseline_end]
    X = sm.add_constant(base[CLIMATE_VARS])
    model = sm.OLS(base["water_ha"], X).fit()
    coef, pc = float(model.params["water_balance"]), float(model.pvalues["water_balance"])
    reliable = bool(model.f_pvalue < CLIMATE_P_MAX and coef > 0 and pc < 0.10)
    info = {"r2": float(model.rsquared), "f_p": float(model.f_pvalue), "coef_balance": coef, "p_balance": pc}
    means = base[CLIMATE_VARS].mean()
    if reliable:
        expected = model.predict(sm.add_constant(df[CLIMATE_VARS], has_constant="add"))
        contributions = {v: model.params[v] * (df[v] - means[v]) for v in CLIMATE_VARS}
    else:
        expected = pd.Series(float(base["water_ha"].mean()), index=df.index)
        contributions = {v: pd.Series(0.0, index=df.index) for v in CLIMATE_VARS}
    return ClimateFit(model, baseline_end, float(model.rsquared), expected, contributions, reliable, info)


def _residual(df: pd.DataFrame, baseline_end: int) -> tuple[ClimateFit, pd.Series]:
    fit = fit_climate(df, baseline_end)
    return fit, df["water_ha"] - fit.expected


# ---------------------------------------------------------------- analisis
def analyze_body(body_id: str, series: pd.DataFrame, suspects: pd.DataFrame,
                 control_id: str | None, baseline_end: int, upstream: str = "") -> dict:
    df = _prep(series[series.body_id == body_id])
    years = df.index.values
    span = years[-1] - years[0]
    base_mean = float(df.loc[:baseline_end, "water_ha"].mean())

    trend = mann_kendall(df["water_ha"])
    total_slope = sen_slope(years, df["water_ha"])

    fit, resid = _residual(df, baseline_end)
    resid_mk = mann_kendall(resid)
    resid_slope = sen_slope(years, resid)
    clim_slope = sen_slope(years, fit.expected)

    # Prueba 1: el clima no alcanza a explicar la perdida
    resid_pct = 100 * resid_slope * span / base_mean if base_mean else 0.0
    t1 = resid_mk["p"] < ALPHA and resid_pct <= -MIN_EFFECT_PCT
    ci = fit.info
    test1 = {
        "pass": bool(t1) if fit.reliable else None,
        "detail": f"Lo que el clima no explica tiene una tendencia de {resid_pct:+.0f}% de la media base en {span} anos "
                  f"(p={resid_mk['p']:.3f}; hace falta p<0.05 y al menos -{MIN_EFFECT_PCT}%). "
                  f"R2 del modelo de clima = {fit.r2:.2f}.",
        "p": resid_mk["p"],
    }
    if not fit.reliable:
        test1["detail"] = (f"No evaluable: el modelo lluvia-evaporacion no explica el agua de esta laguna "
                           f"(p={ci['f_p']:.2f}, R2={ci['r2']:.2f}"
                           + (", y sale con efecto al reves" if ci["coef_balance"] <= 0 else "") +
                           "). Las otras dos pruebas usan el agua observada; la gemela controla el clima.")

    # Prueba 2: la gemela de control no cae igual
    test2 = {"pass": False, "detail": "Sin gemela de control asignada.", "p": None}
    if control_id and (series.body_id == control_id).any():
        cdf = _prep(series[series.body_id == control_id])
        _, cres = _residual(cdf, baseline_end)
        cbase = float(cdf.loc[:baseline_end, "water_ha"].mean())
        diff = (resid / base_mean - cres / cbase).dropna() * 100  # puntos porcentuales
        dmk = mann_kendall(diff)
        dslope = sen_slope(diff.index.values, diff)
        t2 = dmk["p"] < ALPHA and dslope < 0
        test2 = {
            "pass": bool(t2),
            "detail": f"Frente a su gemela pierde {dslope*span:+.1f} puntos % extra (p={dmk['p']:.3f}).",
            "p": dmk["p"],
        }
        # una gemela solo sirve de referencia si se mantuvo estable: si gano o perdio mas del 25% de su agua,
        # la comparacion no es valida (por ejemplo, un lago alimentado por deshielo que crece)
        twin_change = 100 * (cdf["water_ha"].iloc[-5:].mean() - cbase) / cbase if cbase else 0.0
        if abs(twin_change) > TWIN_MAX_CHANGE:
            test2 = {"pass": None, "p": dmk["p"],
                     "detail": f"No evaluable: la gemela no es estable (cambio su agua {twin_change:+.0f}%), "
                               "asi que no sirve de referencia."}

    # Auditoria de sospechosos + Prueba 3 (coincidencia en el tiempo)
    cp_idx, cp_p = pettitt(resid.values)
    resid_break = int(years[cp_idx]) if cp_p < 0.1 else None
    ranked = audit_suspects(df, resid, suspects[suspects.body_id == body_id], resid_break, baseline_end)
    direct = [x for x in ranked if not x["indirect"] and x["big_enough"]]
    top = direct[0] if direct else (ranked[0] if ranked else None)
    # pasa solo con un sospechoso directo que crece antes de la caida y se relaciona con ella
    t3 = bool(top and not top["indirect"] and top["precedes"] and top["p"] < ALPHA and top["rho"] < 0)
    test3 = {
        "pass": t3,
        "detail": (f"El residuo cambia en {resid_break}; {top['label'].lower()} empieza a crecer en {top['onset']}."
                   if top and resid_break else "No se detecta un quiebre claro en el residuo."),
        "p": top["p"] if top else None,
    }

    n_pass = sum(bool(t["pass"]) for t in (test1, test2, test3))
    confidence = {3: "Alta", 2: "Media"}.get(n_pass, "Baja")

    # Descomposicion del cambio: promedio de los ultimos 5 anos menos el promedio del periodo base.
    # Es la misma medida que el % de la tarjeta, y las partes suman exactamente el total.
    last, base_idx = df.index[-5:], df.loc[:baseline_end].index
    total_change = float(df["water_ha"].loc[last].mean() - base_mean)
    groups = {}
    for g, vs in CLIMATE_GROUPS.items():
        c = sum(fit.contributions[v] for v in vs)
        groups[g] = float(c.loc[last].mean() - c.loc[base_idx].mean())
    resid_change = float(resid.loc[last].mean() - resid.loc[base_idx].mean())
    human = resid_change if (test3["pass"] and n_pass >= 2) else 0.0
    decomposition = {**groups, "Huella humana": human, STATE_UNKNOWN: resid_change - human}
    clim_change = sum(groups.values())
    climate_share = clim_change / total_change if (total_change < 0 and fit.reliable) else None

    change_pct = 100 * total_change / base_mean if base_mean else 0.0
    falls = change_pct <= -MIN_EFFECT_PCT
    rising = pressure_rising(suspects[suspects.body_id == body_id], df.index[-15:])
    if test3["pass"] and n_pass >= 2:
        state = "Huella humana"
    elif falls and fit.reliable and climate_share is not None and climate_share >= CLIMATE_SHARE_MIN:
        state = "Causa climatica"
    elif falls:
        state = STATE_UNKNOWN
    elif rising:
        state = "Alerta temprana"
    else:
        state = "Intacto"

    quality = data_quality(df)
    if quality["level"] == "baja" and n_pass >= 2:
        confidence = {"Alta": "Media", "Media": "Baja"}[confidence]  # datos dudosos: se baja un nivel

    # por que: motivos legibles del veredicto (sobre todo cuando es incalculable)
    why = []
    if not fit.reliable:
        why.append(f"El efecto del clima no se puede calcular con confianza: el modelo lluvia-evaporacion no es "
                   f"significativo para esta laguna (p={ci['f_p']:.2f}, R2={ci['r2']:.2f}).")
    elif climate_share is not None and climate_share < CLIMATE_SHARE_MIN and state == STATE_UNKNOWN:
        why.append(f"El clima explica solo el {100 * climate_share:.0f}% de la perdida.")
    if test2["pass"] is None and "gemela" in test2["detail"]:
        why.append(test2["detail"].replace("No evaluable: ", "").capitalize())
    if test2["pass"] is False:
        why.append("Sin gemela de control." if test2["p"] is None else
                   "La laguna no pierde mas que su gemela de control: no se puede descartar un efecto regional.")
    if not test3["pass"]:
        if n_pass >= 2:
            why.append("El clima no la explica y la gemela no la sufre, pero ningun sospechoso medido la explica mas "
                       "alla del paso del tiempo: puede haber una causa humana no medida (extraccion, desvio).")
        else:
            why.append("Ningun sospechoso directo crecio antes de la caida y se relaciona con ella mas alla del "
                       "paso del tiempo.")
    if test3["pass"] and state == STATE_UNKNOWN:
        why.append(f"Pista: {top['label'].lower()} crece antes de la caida y se relaciona con ella, pero falta una "
                   "segunda prueba (clima o gemela) para afirmar que es la causa.")
    if quality["level"] == "baja":
        why.append(f"La serie de agua es de calidad baja (Landsat contra JRC r={quality['r_jrc']:.2f}).")
    if upstream:
        why.append(f"Recibe agua por rio desde {upstream}: el caudal solo se estima con satelite (agua en el cauce), "
                   "sin estaciones de caudal en el analisis.")
    if state == "Huella humana" and not fit.reliable:
        why.insert(0, "Confianza limitada: el clima no se pudo medir y el veredicto se apoya en la gemela y la "
                      "coincidencia en el tiempo.")
    if falls and change_pct > -SMALL_EFFECT_PCT:
        confidence = "Baja"  # un efecto apenas sobre el umbral es fragil
        why.append(f"La perdida es pequena ({change_pct:+.0f}%), cerca del umbral del 10%: el veredicto es fragil.")

    return {
        "body_id": body_id,
        "years": [int(y) for y in years],
        "observed": [round(float(v), 1) for v in df["water_ha"]],
        "expected": [round(float(v), 1) for v in fit.expected],
        "oni": [round(float(v), 2) for v in df["oni"]],
        "baseline_end": baseline_end,
        "baseline_mean_ha": round(base_mean, 1),
        "trend": {**trend, "sen_ha_per_year": total_slope,
                  "change_pct": 100 * (df["water_ha"].iloc[-5:].mean() - base_mean) / base_mean if base_mean else 0.0},
        "climate_r2": fit.r2,
        "tests": {"clima": test1, "control": test2, "coincidencia": test3},
        "climate_share": climate_share,
        "climate_reliable": fit.reliable,
        "climate_fit": ci,
        "why": why,
        "data_quality": quality,
        "n_pass": n_pass,
        "confidence": confidence,
        "decomposition_ha": {k: round(float(v), 1) for k, v in decomposition.items()},
        "suspects": ranked,
        "state": state,
        "backtest": backtest(df, baseline_end),
    }


def _excess(s: pd.Series, baseline_end: int, cumulative: bool) -> pd.Series:
    """Presion por encima de su ritmo base.

    Desmonte y fuego dejan efecto acumulado, pero la suma acumulada de cualquier serie positiva
    siempre sube; por eso se acumula solo el exceso sobre el ritmo del periodo base (o de los
    primeros 5 anos con dato, si el dataset empieza despues, como Hansen en 2001).
    """
    ref = s.loc[:baseline_end]
    if (ref > 0).sum() < 5:
        ref = s[s > 0].iloc[:5]
    ex = s - (ref.mean() if len(ref) else 0.0)
    return ex.cumsum() if cumulative else ex


AREA_TAG = {"subcuenca_local": "cerca", "cuenca_aporte": "cuenca"}


def base_name(name: str) -> str:
    """'mining_ha@cuenca' -> 'mining_ha'."""
    return name.split("@")[0]


def suspect_label(name: str) -> str:
    base, _, area = name.partition("@")
    lab = SUSPECT_LABELS.get(base, base)
    return f"{lab} ({area})" if area else lab


def tag_areas(sus: pd.DataFrame) -> pd.DataFrame:
    """Si un cuerpo de agua tiene sospechosos medidos en dos escalas, cada escala es un sospechoso aparte."""
    if "area" not in sus or sus.empty:
        return sus
    sus = sus.copy()
    multi = sus.groupby("body_id")["area"].transform("nunique") > 1
    sus.loc[multi, "suspect"] = sus.loc[multi, "suspect"] + "@" + sus.loc[multi, "area"].map(AREA_TAG).fillna("")
    return sus


CONTEXT_ONLY = {"natural_water_ha", "desaguadero_water_ha"}  # series de contexto que no son sospechosos


FLOWS = {"forest_loss_ha", "burned_ha"}  # hectareas por ano: se acumulan
# Indicadores indirectos: crecen en casi todas partes (poblacion, luz, ciudad de toda la cuenca) y se
# correlacionan con cualquier caida. Se muestran, pero no pueden ser el culpable ni pasar la prueba 3 solos.
INDIRECT = {"population", "night_lights"}


def is_indirect(name: str) -> bool:
    base, _, area = name.partition("@")
    return base in INDIRECT or (base == "urban_ha" and area == "cuenca")


def _detrend(x: pd.Series) -> pd.Series:
    t = np.arange(len(x), dtype=float)
    b = np.polyfit(t, x.values.astype(float), 1)
    return pd.Series(x.values - np.polyval(b, t), index=x.index)
MIN_SHARE_OF_LOSS = 0.10   # un sospechoso de area debe crecer al menos el 10% del agua perdida
PRE_GROWTH = 1.5           # y, para anteceder, haber crecido 1.5 veces antes del quiebre del agua


def audit_suspects(df, resid, sus: pd.DataFrame, resid_break: int | None, baseline_end: int) -> list[dict]:
    """Ordena los sospechosos por evidencia.

    Tres criterios (cada uno suma): crece de forma significativa; antecede la caida (ya habia crecido
    PRE_GROWTH veces antes del quiebre del agua); y se relaciona en el sentido esperado (mas presion,
    menos agua de la que explica el clima). Ademas, un sospechoso medido en hectareas que crecio menos
    del 10% del agua perdida es demasiado chico para explicarla: su evidencia queda en debil.
    """
    base_mean = float(df.loc[:baseline_end, "water_ha"].mean())
    water_lost = max(0.0, base_mean - float(df["water_ha"].iloc[-5:].mean()))
    out = []
    for name, g in sus.groupby("suspect"):
        bn = base_name(name)
        if bn in CONTEXT_ONLY:
            continue
        s = g.set_index("year")["value"].reindex(df.index).fillna(0.0)
        if s.std() == 0:
            continue
        rising = mann_kendall(s)["p"] < ALPHA and sen_slope(s.index.values, s) > 0
        level = s.cumsum() if bn in FLOWS else s  # area acumulada para desmonte y fuego
        pressure = _excess(s, baseline_end, bn in FLOWS)
        idx, _ = pettitt(s.values)
        onset = int(df.index[idx])
        rho, p = stats.spearmanr(pressure, resid)
        r2 = float(rho**2)
        # relacion mas alla del paso del tiempo: correlacion entre las series sin su tendencia lineal.
        # Si dos cosas solo crecen y bajan "con los anos", aqui no aparecen relacionadas.
        rho_dt, p_dt = stats.spearmanr(_detrend(pressure), _detrend(resid))
        early = float(level.iloc[:5].mean())
        growth = float(level.iloc[-5:].mean() - early)
        is_area = bn.endswith("_ha")
        big_enough = (not is_area) or water_lost == 0 or growth >= MIN_SHARE_OF_LOSS * water_lost
        precedes = False
        if rising and resid_break is not None:
            # nivel alrededor del quiebre (el ano anterior al siguiente): como en la regla original, el
            # sospechoso puede arrancar el mismo ano en que se quiebra el agua
            pre = float(level.loc[resid_break - 1:resid_break + 1].mean())
            min_abs = MIN_SHARE_OF_LOSS * water_lost if is_area else 0.0
            precedes = pre >= PRE_GROWTH * max(early, 1e-9) and (pre - early) >= min_abs
        relation = bool(p < ALPHA and rho < 0 and r2 > 0.3)  # rho_dt (sin tendencia) se reporta como dato
        indirect = is_indirect(name)
        hits = sum([precedes, rising, relation])
        evidence = {3: "fuerte", 2: "media"}.get(hits, "debil") if big_enough else "debil"
        if indirect and evidence == "fuerte":
            evidence = "media"  # un indicador indirecto nunca es evidencia fuerte
        out.append({
            "suspect": name,
            "label": suspect_label(name),
            "onset": onset,
            "rho": float(rho),
            "p": float(p),
            "r2": r2,
            "precedes": bool(precedes),
            "rising": bool(rising),
            "growth": round(growth, 1),
            "share_of_loss": round(growth / water_lost, 2) if is_area and water_lost else None,
            "big_enough": bool(big_enough),
            "indirect": bool(indirect),
            "rho_detrended": float(rho_dt),
            "relation_beyond_trend": bool(p_dt < 0.10 and rho_dt < 0),
            "evidence": evidence,
            "score": (hits if big_enough else 0) + r2 - (2 if indirect else 0),
        })
    out.sort(key=lambda d: d["score"], reverse=True)
    # sospechosos que crecen juntos: se reportan como inseparables
    for a in out:
        a["together_with"] = [b["label"] for b in out if b is not a and b["evidence"] == a["evidence"] != "debil"
                              and abs(b["onset"] - a["onset"]) <= 2]
    return out


# solo el cambio de uso del suelo dispara la alerta; poblacion y luces crecen en casi todas partes
ALERT_SUSPECTS = {"mining_ha", "agri_ha", "pasture_ha", "urban_ha", "forest_loss_ha", "dry_crop_ha",
                  "artificial_water_ha", "mining_water_ha", "human_land_ha"}
ALERT_GROWTH = 1.5   # el sospechoso debe crecer al menos 1.5 veces
ALERT_MIN_HA = 50    # y en al menos 50 ha


def pressure_rising(sus: pd.DataFrame, recent) -> bool:
    """Presion humana creciendo de verdad en los ultimos 15 anos: tendencia significativa,
    al menos 1.5 veces lo que habia al inicio de la ventana y al menos 50 ha mas."""
    for name, g in sus.groupby("suspect"):
        if base_name(name) not in ALERT_SUSPECTS:
            continue
        s = g.set_index("year")["value"].reindex(recent).fillna(0.0)
        if s.std() == 0 or mann_kendall(s)["p"] >= ALPHA or sen_slope(recent, s) <= 0:
            continue
        early, late = s.iloc[:5].mean(), s.iloc[-5:].mean()
        if late - early >= ALERT_MIN_HA and late >= ALERT_GROWTH * max(early, 1e-9):
            return True
    return False


def data_quality(df) -> dict:
    """Calidad de la serie de agua: coincidencia de Landsat con JRC y anos interpolados."""
    out = {"level": "sin validar", "r_jrc": None, "interpolated_years": []}
    if "nodata_pct" in df:
        out["interpolated_years"] = [int(y) for y in df.index[df["nodata_pct"] > 20]]
    if "water_ha_jrc" in df and df["water_ha_jrc"].notna().sum() > 5:
        both = df[["water_ha", "water_ha_jrc"]].dropna()
        r = float(both["water_ha"].corr(both["water_ha_jrc"]))
        out["r_jrc"] = r
        out["level"] = "alta" if r >= 0.85 else "media" if r >= 0.7 else "baja"
    return out


def backtest(df, baseline_end: int) -> dict:
    """Validacion con el pasado: entrenar hasta baseline_end y medir el error despues.

    Solo tiene sentido en cuerpos de agua sin huella humana (controles); en los demas
    el error alto ES la senal.
    """
    fit = fit_climate(df, baseline_end)
    after = df.loc[baseline_end + 1:]
    if after.empty:
        return {}
    err = after["water_ha"] - fit.expected.loc[after.index]
    return {"mae_ha": float(err.abs().mean()), "bias_ha": float(err.mean()),
            "mae_pct": float(100 * err.abs().mean() / df["water_ha"].mean())}


def run(bodies: pd.DataFrame, series: pd.DataFrame, suspects: pd.DataFrame, baseline_end: int = 2000,
        *, conservative: bool = False) -> list[dict]:
    suspects = tag_areas(suspects)
    if conservative:
        from . import safeguarded
    results = []
    for _, b in bodies.iterrows():
        ctrl = b.get("control_id")
        ctrl = ctrl if isinstance(ctrl, str) and ctrl else None
        up = b.get("upstream_bodies", "")
        up = up if isinstance(up, str) else ""
        if conservative:
            r = safeguarded.analyze_body(b.body_id, series, suspects, ctrl, baseline_end)
        else:
            r = analyze_body(b.body_id, series, suspects, ctrl, baseline_end, up)
        r.update({"name": b["name"], "lat": float(b.lat), "lon": float(b.lon), "kind": b.kind,
                  "department": b.get("department", ""), "control_id": ctrl})
        results.append(r)
    # correccion por pruebas multiples sobre la tendencia de todos los cuerpos de agua
    adj = holm({r["body_id"]: r["trend"]["p"] for r in results})
    for r in results:
        r["trend"]["p_holm"] = adj[r["body_id"]]
    return safeguarded.adjust_evidence(results) if conservative else results
