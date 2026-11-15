# Evaluación conservadora del motor

Selección temporal dentro del período base hasta 2000; evaluación posterior con datos revisados y observaciones de agua imputadas excluidas. No se extraen nuevos datos de servicios externos.

| Cuerpo | Modelo | Estado | MAE (ha) | MAE / media base | Cobertura banda 80% |
|---|---|---|---:|---:|---:|
| poopo | dinamico_ar1 | Sin perdida anomala detectada | 36490.71 | 18.9% | 100.0% |
| uru_uru | dinamico_ar1 | Sin perdida anomala detectada | 3319.03 | 37.6% | 82.6% |
| concepcion | ridge | Sin perdida anomala detectada | 2476.29 | 41.6% | 39.1% |
| titicaca_menor | dinamico_ar1 | Sin perdida anomala detectada | 4017.77 | 4.7% | 91.3% |
| pozuelos | climatologia | Sin perdida anomala detectada | 3074.57 | 46.7% | 100.0% |
| chiquitania_este | climatologia | Perdida no explicada | 254.06 | 57.9% | 0.0% |
| andino_peru | dinamico_ar1 | Sin perdida anomala detectada | 880.19 | 33.1% | 91.3% |
| san_matias | ols | Sin perdida anomala detectada | 36.97 | 2.7% | 13.0% |

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

Se ejecutaron 9 escenarios de fecha placebo en controles candidatos. Sus alarmas no se denominan falsos positivos confirmados: falta verificar que esos cuerpos no estén intervenidos. No se reportan precisión, recall o F1 de atribución sin etiquetas independientes.

No se ejecutó una atribución causal confirmatoria en uno o dos lagos reales: faltan fecha y evidencia independiente de una intervención. El motor acepta esos registros explícitos cuando existan; no toma un quiebre detectado en la misma serie como prueba externa.

## Archivos

`model_comparison.csv`: todas las alternativas y cortes de selección; `summary.csv`: modelo elegido; `data_quality.csv`, `series_quality.csv` y `suspects_quality.csv`: trazabilidad; `candidate_control_placebos.csv`: pruebas exploratorias; `policy_used.json`: parámetros exactos. Los resultados previos se conservan en `history/results_pre_validation_v2.json` y las corridas SQLite existentes no se borran.
