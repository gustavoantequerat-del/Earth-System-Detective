"""Exportación de calidad, comparación de modelos y placebos exploratorios."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from . import validation

def write(src, bodies, series, suspects, results, baseline_end):
    out = Path(src) / "validation"
    out.mkdir(exist_ok=True)
    rows = []
    quality = []
    for r in results:
        for m in r["model_comparison"]:
            rows.append({"body_id": r["body_id"], **m, "normalization_mean_ha": r["baseline_mean_ha"]})
        quality.append({"body_id": r["body_id"], **{k:v for k,v in r["quality"].items() if not isinstance(v, (list, dict))},
                        "state": r["state"], "selected_model": r["selected_model"],
                        "control_eligible": r["control_validation"]["eligible"], "cv_n": r["model_validation"]["cv_n"]})
    pd.DataFrame(rows).to_csv(out / "model_comparison.csv", index=False)
    pd.DataFrame(quality).to_csv(out / "data_quality.csv", index=False)
    enriched = series.copy()
    enriched["water_imputed_inferred"] = enriched.get("nodata_pct", pd.Series(0., index=enriched.index)).gt(20) | enriched.water_ha.isna()
    enriched["water_status"] = np.where(enriched.water_imputed_inferred, "excluded_from_fit_and_tests", "legacy_observed_or_unflagged")
    enriched.to_csv(out / "series_quality.csv", index=False)
    exposures = suspects.copy()
    if "value_status" not in exposures:
        exposures["value_status"] = "legacy_unverified"
    exposures["legacy_zero_not_verified_absence"] = exposures.value.eq(0) & exposures.value_status.eq("legacy_unverified")
    exposures.to_csv(out / "suspects_quality.csv", index=False)
    cfg = validation.policy()
    # Fechas placebo en controles CANDIDATOS: no se presentan como verdad de ausencia de intervención.
    placebos = []
    controls = sorted(set(bodies.control_id.dropna()) - {""})
    for control_id in controls:
        d = validation.prepare(series.loc[series.body_id.eq(control_id)])
        for cut in [2000, 2005, 2010]:
            fit = validation.fit_selected(d, cut, cfg)
            post = d.loc[(d.index > cut) & ~d.water_imputed & d.water_ha.notna()]
            residual = post.water_ha - fit["expected"].loc[post.index]
            trend = validation.block_trend(residual)
            base = float(d.loc[(d.index <= cut) & ~d.water_imputed, "water_ha"].mean())
            effect = 100 * (float(residual.iloc[-5:].mean()) if len(residual) else 0) / max(base, 1e-8)
            below = (post.water_ha < fit["lower"].loc[post.index]).to_numpy()
            # Conservar continuidad anual incluso si se excluyen observaciones.
            run = longest = 0; previous = None
            for year, low in zip(post.index, below):
                run = run+1 if low and previous == year-1 else int(low)
                longest = max(longest, run); previous = year
            alarm = trend["tau"] < 0 and trend["p"] < .05 and effect <= -cfg["min_effect_pct"] and longest >= cfg["consecutive_low_years"]
            placebos.append({"control_id": control_id, "pseudo_cutoff": cut, "selected_model": fit["selected"],
                             "model_reliable": fit["reliable"], "alarm": bool(alarm), "coverage": fit["coverage"],
                             "reviewed_as_unaffected": bool(cfg["control_reviews"].get(control_id, {}).get("approved", False)),
                             "warning": "Exploratorio; control no confirmado. No es tasa validada de falsos positivos."})
    pd.DataFrame(placebos).to_csv(out / "candidate_control_placebos.csv", index=False)
    summary = [{"body_id": r["body_id"], "modelo": r["selected_model"], "estado": r["state"],
                "cv_n": r["model_validation"]["cv_n"], "mae_ha": r["backtest"]["mae_ha"],
                "mae_base_pct": r["backtest"]["mae_pct"], "coverage": r["backtest"]["coverage"]} for r in results]
    pd.DataFrame(summary).to_csv(out / "summary.csv", index=False)
    (out / "policy_used.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    header = "| Cuerpo | Modelo | Estado | MAE (ha) | MAE / media base | Cobertura banda 80% |\n|---|---|---|---:|---:|---:|\n"
    table = "\n".join(f"| {r['body_id']} | {r['modelo']} | {r['estado']} | {r['mae_ha']:.2f} | {r['mae_base_pct']:.1f}% | {r['coverage']:.1%} |" for r in summary)
    (out / "REPORT.md").write_text(f"""# Evaluación conservadora del motor

Selección temporal dentro del período base hasta {baseline_end}; evaluación posterior con datos revisados y observaciones de agua imputadas excluidas. No se extraen nuevos datos de servicios externos.

{header}{table}

## Qué cambió

- Se comparan climatología, OLS, Ridge (penalización fija 1 sobre entradas estandarizadas) y regresión climática con memoria AR(1) residual. Se selecciona por MAE en bloques futuros de dos años dentro del período base; mínimo diez observaciones iniciales.
- El modelo dinámico propaga el residuo desde el último año de entrenamiento; no usa agua observada posterior para formar su contrafactual. Las covariables climáticas posteriores sí son observadas: es una comparación condicional retrospectiva, no un pronóstico operativo de clima.
- Las bandas nominales de 80% se obtienen con bootstrap de residuos en bloques de tres. Son aproximadas, no intervalos calibrados garantizados. Su cobertura se muestra fuera de entrenamiento; elegir el modelo y evaluar su banda requiere más historia de validación independiente.
- El MAE porcentual ahora se normaliza por la media del agua de entrenamiento, no por la media de toda la serie. No es directamente comparable con el antiguo campo porcentual; el MAE en hectáreas también cambia al excluir imputaciones.
- La primera lluvia rezagada queda ausente y no se rellena con lluvia del mismo año; por ello el análisis comienza un año después de la fuente original.
- El agua marcada con más de 20% sin datos o con bandera explícita de imputación no entrena ni determina pruebas. La tabla de calidad conserva las 320 filas de entrada y sus banderas; otras interpolaciones heredadas pueden no estar identificadas.
- Las presiones ausentes no se convierten en cero en el motor. Los ceros heredados no se reinterpretan como ausencias verificadas y están marcados en la exportación.
- La asociación de presión exige signo negativo, crecimiento y antecedencia, con corrección de Holm. Se calcula sobre cambios anuales y se contrasta con desplazamientos circulares; los p son exploratorios y tienen baja resolución con 40 años. Las tendencias usan permutaciones de bloques; esto no demuestra causalidad ni elimina toda dependencia temporal.
- Los p de las pruebas climáticas y de control se corrigen además entre cuerpos de agua. Los intervalos no son simultáneos entre lagos.
- Una pérdida residual no se reparte numéricamente como huella humana. Se conserva como diferencia de tendencias no atribuida.
- Si gana la climatología, puede detectar cambios frente a la referencia, pero no se habilita atribución humana: una media constante no demuestra haber descontado efectos climáticos.

## Controles y casos documentados

La revisión independiente de controles y las intervenciones documentadas están en `config/evidence_policy.json`. Ambos registros empiezan vacíos porque el repositorio no aporta confirmaciones suficientes. Las notas de configuración o los estados previos no son etiquetas independientes de verdad.

Las comparaciones con los controles candidatos se publican, pero la prueba de atribución queda no evaluable hasta documentar elegibilidad. Los umbrales de error, cobertura, similitud y tamaño de efecto son provisionales y configurables; no son estándares universales.

Se ejecutaron {len(placebos)} escenarios de fecha placebo en controles candidatos. Sus alarmas no se denominan falsos positivos confirmados: falta verificar que esos cuerpos no estén intervenidos. No se reportan precisión, recall o F1 de atribución sin etiquetas independientes.

No se ejecutó una atribución causal confirmatoria en uno o dos lagos reales: faltan fecha y evidencia independiente de una intervención. El motor acepta esos registros explícitos cuando existan; no toma un quiebre detectado en la misma serie como prueba externa.

## Archivos

`model_comparison.csv`: todas las alternativas y cortes de selección; `summary.csv`: modelo elegido; `data_quality.csv`, `series_quality.csv` y `suspects_quality.csv`: trazabilidad; `candidate_control_placebos.csv`: pruebas exploratorias; `policy_used.json`: parámetros exactos. Los resultados previos se conservan en `history/results_pre_validation_v2.json` y las corridas SQLite existentes no se borran.
""", encoding="utf-8")
