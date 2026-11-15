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
# memoria del lago: anos de lluvia menos evaporacion acumulados. No se elige "la mejor" (con 16 anos de base eso
# sobreajusta y hace saltar los veredictos): se corre con cada memoria y se vota. Un veredicto que se mantiene
# en casi todas las memorias es robusto; uno que cambia es fragil y su confianza baja.
MEMORY_YEARS = (1, 2, 3, 4, 6, 8)
MEMORY_DEFAULT = 2
ROBUST_MIN = 5   # de 6 memorias: robusto
FRAGILE_MAX = 3  # 3 o menos de 6: fragil, confianza baja
STATE_UPSTREAM = "Aguas arriba"
UPSTREAM_GROUP = "Menos agua desde aguas arriba"
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
    "river_green_ha": "Riego en epoca seca",
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
    # en lagos poco profundos se usa la evaporacion sobre el propio lago (uma/hydro_extra.py --lake-pet)
    pet = "pet_lake_mm" if "pet_lake_mm" in df and df["pet_lake_mm"].notna().sum() > 10 else "pet_mm"
    if pet in df and df[pet].notna().sum() > 10:
        wb = _z(df["precip_mm"]) - _z(df[pet].interpolate(limit_direction="both"))
    else:  # sin evaporacion potencial: solo lluvia
        wb = _z(df["precip_mm"])
    df["water_balance"] = wb + wb.shift(1).bfill()
    for k in MEMORY_YEARS:  # balance acumulado de k anos: los lagos grandes o terminales tardan anos en responder
        df[f"wb_{k}"] = wb.rolling(k, min_periods=1).sum()
    return df.set_index("year")


def fit_climate(df: pd.DataFrame, baseline_end: int, extra: tuple[str, ...] = ()) -> ClimateFit:
    """Ajusta agua ~ balance de agua (2 anos) + ONI solo en el periodo base.

    Entrenar solo en el periodo base evita que el modelo de clima absorba la tendencia humana posterior.
    El modelo es confiable si es significativo (p < 0.05) y si mas balance de agua da mas agua (efecto
    positivo, p < 0.10). Si no lo es, no se usa para atribuir: el agua esperada queda en el promedio base.
    """
    vars_ = CLIMATE_VARS + list(extra)
    base = df.loc[:baseline_end]
    X = sm.add_constant(base[vars_])
    model = sm.OLS(base["water_ha"], X).fit()
    coef, pc = float(model.params["water_balance"]), float(model.pvalues["water_balance"])
    # con aporte de aguas arriba, la lluvia ya llega en buena parte por el rio: se exige que el aporte cuente
    key = extra[0] if extra else "water_balance"
    kc, kp = float(model.params[key]), float(model.pvalues[key])
    reliable = bool(model.f_pvalue < CLIMATE_P_MAX and kc > 0 and kp < 0.10)
    info = {"r2": float(model.rsquared), "r2_adj": float(model.rsquared_adj), "f_p": float(model.f_pvalue),
            "coef_balance": coef, "p_balance": pc}
    if extra:
        info.update({"coef_upstream": kc, "p_upstream": kp})
    means = base[vars_].mean()
    if reliable:
        expected = model.predict(sm.add_constant(df[vars_], has_constant="add"))
        contributions = {v: model.params[v] * (df[v] - means[v]) for v in vars_}
    else:
        expected = pd.Series(float(base["water_ha"].mean()), index=df.index)
        contributions = {v: pd.Series(0.0, index=df.index) for v in vars_}
    return ClimateFit(model, baseline_end, float(model.rsquared), expected, contributions, reliable, info)


_MEMORY = {"k": 2}  # anos de memoria de la corrida actual (run_ensemble recorre MEMORY_YEARS)


def _residual(df: pd.DataFrame, baseline_end: int) -> tuple[ClimateFit, pd.Series]:
    k = _MEMORY["k"]
    df["water_balance"] = df[f"wb_{k}"]
    fit = fit_climate(df, baseline_end)
    fit.info["memoria_anos"] = k
    if "upstream" in df and df["upstream"].notna().sum() > 20:
        up = fit_climate(df, baseline_end, ("upstream",))
        # se usa el aporte de aguas arriba solo si es significativo y explica mejor que la lluvia local sola
        if up.reliable and (not fit.reliable or up.info["r2_adj"] > fit.info["r2_adj"]):
            fit = up
    return fit, df["water_ha"] - fit.expected


# ---------------------------------------------------------------- analisis
def analyze_body(body_id: str, series: pd.DataFrame, suspects: pd.DataFrame,
                 control_id: str | None, baseline_end: int, upstream: str = "",
                 upstream_water: pd.Series | None = None, upstream_label: str = "al lago que la alimenta por rio") -> dict:
    df = _prep(series[series.body_id == body_id])
    if upstream_water is not None:  # agua del lago que la alimenta por rio (observada)
        df["upstream"] = _z(upstream_water.reindex(df.index).interpolate(limit_direction="both"))
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
    for g, vs in {**CLIMATE_GROUPS, **({UPSTREAM_GROUP: ["upstream"]} if "upstream" in fit.contributions else {})}.items():
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
        # si la mayor parte llega por el rio, la causa esta en la fuente (ver su propio veredicto)
        state = STATE_UPSTREAM if groups.get(UPSTREAM_GROUP, 0) < 0.5 * clim_change else "Causa climatica"
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
    if "upstream" in fit.contributions and falls:
        up_ha = -groups[UPSTREAM_GROUP]
        size = ("mas que toda la perdida" if up_ha >= -total_change else
                f"el {100 * up_ha / -total_change:.0f}% de la perdida")
        why.append(f"El agua sigue {upstream_label}: con esa entrada el modelo explica R2={ci['r2']:.2f} "
                   f"(p={ci['f_p']:.3f}). La menor llegada de agua equivale a {up_ha:,.0f} ha, {size} "
                   f"({-total_change:,.0f} ha). Lo que queda sin explicar es lo que pasa en el camino o en la laguna.")
        if climate_share is not None and climate_share > 1.3:
            why.append("La laguna tiene mas agua de la que predice su fuente: algo le suma agua (por ejemplo aguas "
                       "servidas o un aporte no medido).")
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
    if upstream and "upstream" not in fit.contributions:
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


AREA_TAG = {"subcuenca_local": "cerca", "cuenca_aporte": "cuenca", "rio": "rio"}


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


FLOWS = {"forest_loss_ha", "burned_ha"}
# primer ano con datos reales: Hansen (desmonte) y MODIS (incendios, agua de cultivos) empiezan en 2001. Antes
# no hay medicion, no "cero": rellenar con ceros hacia parecer que todos empiezan a crecer en 2001.
DATA_START = {"forest_loss_ha": 2001, "burned_ha": 2001, "crop_water_hm3": 2001}
MIN_LEAD_YEARS = 3  # para decir que un sospechoso antecede la caida, debe tener datos al menos 3 anos antes  # hectareas por ano: se acumulan
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
        start = max(DATA_START.get(bn, int(df.index[0])), int(g.year.min()))
        yrs = df.index[df.index >= start]
        s = g.set_index("year")["value"].reindex(yrs).fillna(0.0)
        if s.std() == 0 or len(s) < 8:
            continue
        r_s = resid.loc[yrs]
        rising = mann_kendall(s)["p"] < ALPHA and sen_slope(s.index.values, s) > 0
        level = s.cumsum() if bn in FLOWS else s  # area acumulada para desmonte y fuego
        pressure = _excess(s, min(baseline_end, int(yrs[0]) + 4), bn in FLOWS)
        idx, _ = pettitt(s.values)
        onset = int(yrs[idx])
        rho, p = stats.spearmanr(pressure, r_s)
        r2 = float(rho**2)
        # relacion mas alla del paso del tiempo: correlacion entre las series sin su tendencia lineal.
        # Si dos cosas solo crecen y bajan "con los anos", aqui no aparecen relacionadas.
        rho_dt, p_dt = stats.spearmanr(_detrend(pressure), _detrend(r_s))
        early = float(level.iloc[:5].mean())
        growth = float(level.iloc[-5:].mean() - early)
        is_area = bn.endswith("_ha")
        big_enough = (not is_area) or water_lost == 0 or growth >= MIN_SHARE_OF_LOSS * water_lost
        precedes = False
        if rising and resid_break is not None and resid_break >= int(yrs[0]) + MIN_LEAD_YEARS:
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
            "data_from": int(yrs[0]),
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
        river_inflow: dict[str, tuple[str, pd.Series]] | None = None, *, conservative: bool = False) -> list[dict]:
    """river_inflow: {body_id: (descripcion, serie)} agua medida en el rio justo antes de la laguna. Se usa en vez
    de la superficie del lago fuente cuando el rio no entrega en proporcion a esa superficie (rebalse)."""
    river_inflow = river_inflow or {}
    suspects = tag_areas(suspects)
    if conservative:
        from . import safeguarded
    results = []
    for _, b in bodies.iterrows():
        ctrl = b.get("control_id")
        ctrl = ctrl if isinstance(ctrl, str) and ctrl else None
        up = b.get("upstream_bodies", "")
        up = up if isinstance(up, str) else ""
        src = up.split(",")[-1] if up else ""  # la fuente mas lejana (por ejemplo el Titicaca)
        km2 = {r.body_id: r.get("upstream_km2") for _, r in bodies.iterrows()}
        if src and not (km2.get(src) and km2.get(b.body_id) and km2[src] >= 0.3 * km2[b.body_id]):
            src = ""  # la fuente debe drenar al menos el 30% de la cuenca para dominar el aporte
        upw = series[series.body_id == src].set_index("year")["water_ha"] if src else None
        label = "al lago que la alimenta por rio"
        if src and b.body_id in river_inflow:
            label, upw = river_inflow[b.body_id]
        if conservative:
            r = safeguarded.analyze_body(b.body_id, series, suspects, ctrl, baseline_end)
        else:
            r = analyze_body(b.body_id, series, suspects, ctrl, baseline_end, up,
                             upw if upw is not None and len(upw) else None, label)
        r.update({"name": b["name"], "lat": float(b.lat), "lon": float(b.lon), "kind": b.kind,
                  "department": b.get("department", ""), "control_id": ctrl})
        results.append(r)
    # cadena: si la causa esta aguas arriba, se cita el veredicto de la fuente
    by = {r["body_id"]: r for r in results}
    for r, (_, b) in zip(results, bodies.iterrows()):
        src = (b.get("upstream_bodies") or "").split(",")[-1] if isinstance(b.get("upstream_bodies"), str) else ""
        if r["state"] == STATE_UPSTREAM and src in by:
            s = by[src]
            r["upstream_source"] = {"body_id": src, "name": s["name"], "state": s["state"],
                                    "confidence": s["confidence"]}
            # cadena: la parte humana de lo que no llega es, como mucho, la parte humana de la perdida de la
            # fuente. Con confianza baja en la fuente no hay un punto, hay un rango: de 0 a ese maximo.
            sd = s["decomposition_ha"]
            s_loss = -sum(v for v in sd.values() if v < 0)
            s_human = -min(sd.get("Huella humana", 0.0), 0.0)
            share = max(s_human / s_loss, 0.0) if s_loss else 0.0
            up_loss = -min(r["decomposition_ha"].get(UPSTREAM_GROUP, 0.0), 0.0)
            point = s["confidence"] in ("Alta", "Media")
            # si la fuente no tiene veredicto atribuible (incalculable), la parte humana es desconocida, no cero
            known = s["state"] in ("Huella humana", "Causa climatica", "Intacto")
            r["upstream_split"] = {
                "upstream_ha": round(up_loss), "source_human_share": round(share, 2) if known else None,
                "human_min_ha": (round(up_loss * share) if point else 0) if known else None,
                "human_max_ha": round(up_loss * share) if known else None,
                "source_confidence": s["confidence"]}
            if up_loss:
                if not known:
                    rng = (f"De las {up_loss:,.0f} ha que dejan de llegar, la parte humana todavia no se puede acotar: "
                           f"la fuente tiene veredicto {s['state'].lower()}, asi que no se sabe que parte de su "
                           "propia perdida es humana.")
                else:
                    span = (f"unas {up_loss * share:,.0f} ha" if point else
                            f"entre 0 y {up_loss * share:,.0f} ha ({100 * share:.0f}% como maximo)")
                    rng = (f"De las {up_loss:,.0f} ha que dejan de llegar, la parte humana es {span}: la fuente "
                           f"atribuye a la accion humana el {100 * share:.0f}% de su propia perdida, con "
                           f"confianza {s['confidence'].lower()}.")
                r["why"].insert(1, rng + " Para cerrar el rango hacen falta el nivel medido del Titicaca y el "
                                         "caudal del Desaguadero en estaciones.")
            r["why"].insert(0, f"La causa esta en la fuente: {s['name']}, que tiene veredicto {s['state'].lower()} "
                               f"(confianza {s['confidence'].lower()}). Lo que le pase a esa fuente le pasa a esta laguna.")
    # correccion por pruebas multiples sobre la tendencia de todos los cuerpos de agua
    adj = holm({r["body_id"]: r["trend"]["p"] for r in results})
    for r in results:
        r["trend"]["p_holm"] = adj[r["body_id"]]
    return safeguarded.adjust_evidence(results) if conservative else results


def run_ensemble(bodies: pd.DataFrame, series: pd.DataFrame, suspects: pd.DataFrame, baseline_end: int = 2000,
                 river_inflow: dict | None = None) -> list[dict]:
    """Corre el motor con cada memoria del lago y vota el veredicto.

    El resultado de cada cuerpo de agua es la corrida con el veredicto mayoritario (la de memoria 2 anos si
    coincide). Se agrega `robustness` con cuantas memorias coinciden; si son pocas, la confianza baja.
    """
    runs = {}
    try:
        for k in MEMORY_YEARS:
            _MEMORY["k"] = k
            runs[k] = {r["body_id"]: r for r in run(bodies, series, suspects, baseline_end, river_inflow)}
    finally:
        _MEMORY["k"] = MEMORY_DEFAULT
    out = []
    for bid in runs[MEMORY_DEFAULT]:
        states = {k: runs[k][bid]["state"] for k in MEMORY_YEARS}
        votes: dict[str, int] = {}
        for st_ in states.values():
            votes[st_] = votes.get(st_, 0) + 1
        top = max(votes.values())
        winners = [st_ for st_, v in votes.items() if v == top]
        # empate: gana la memoria por defecto si esta entre los empatados; si no, la mas cercana
        order = sorted(MEMORY_YEARS, key=lambda k: abs(k - MEMORY_DEFAULT))
        k_rep = next(k for k in order if states[k] in winners)
        r = runs[k_rep][bid]
        agree = votes[r["state"]]
        r["robustness"] = {"agree": agree, "of": len(MEMORY_YEARS), "memory_used": k_rep,
                           "states": {str(k): v for k, v in states.items()}}
        r["climate_fit"]["memoria_anos"] = k_rep
        others = {s_: v for s_, v in votes.items() if s_ != r["state"]}
        if agree <= FRAGILE_MAX:
            r["confidence"] = "Baja"
        if agree < len(MEMORY_YEARS):
            alt = ", ".join(f"{s_.lower()} en {v}" for s_, v in sorted(others.items(), key=lambda x: -x[1]))
            r["why"].append(f"Robustez: el veredicto se mantiene con {agree} de {len(MEMORY_YEARS)} memorias del lago "
                            f"(1 a 8 anos de lluvia acumulada); con las demas sale {alt}."
                            + (" Es un veredicto fragil." if agree <= FRAGILE_MAX else ""))
        out.append(r)
    return out
