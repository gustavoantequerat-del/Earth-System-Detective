# Motor conservador: evaluación y límites

El motor conserva los datos originales y compara climatología, OLS, Ridge y una regresión climática con memoria AR(1) del residuo. La selección utiliza exclusivamente cortes temporales dentro del período base. El agua posterior al corte no entra al ajuste ni a los intervalos; las covariables climáticas posteriores son observadas, por lo que es una evaluación retrospectiva condicional.

## Reproducir

Desde la raíz del repositorio, con el intérprete del proyecto:

```powershell
python -m unittest discover -s tests -v
python run_engine.py data/real 2000 "Evaluacion conservadora" --conservative
```

El argumento 2000 sigue siendo el **final del período base**, no el inicio de un filtro. La lluvia rezagada del primer año no se inventa: el análisis actual comienza en 1986. Las observaciones base de agua marcadas como imputadas se excluyen. Con estos datos quedan 15 observaciones de entrenamiento utilizables por cuerpo y cinco predicciones de validación interna: la selección tiene una base reducida.

Al seleccionar **Modelo conservador** en el dashboard de Next.js se pueden comparar observaciones, referencia
modelada y banda aproximada. Su ficha muestra las alternativas, calidad, elegibilidad de control y evaluación posterior.

## Resultados y trazabilidad

- [Informe real generado](data/real/validation/REPORT.md).
- [Comparación de modelos](data/real/validation/model_comparison.csv).
- [Resumen por cuerpo](data/real/validation/summary.csv).
- [Calidad del agua](data/real/validation/series_quality.csv) y [presiones heredadas](data/real/validation/suspects_quality.csv).
- [Placebos en controles candidatos](data/real/validation/candidate_control_placebos.csv).
- [Política efectivamente usada](data/real/validation/policy_used.json).

Las corridas conservadoras usan `data/real/validation/results.json` y `data/real/validation/uma.db`. La huella
de código incluye los módulos del modelo y la política. Los diagnósticos completos se guardan en
`diagnostics`. El JSON previo a la evaluación original está en `data/real/history/results_pre_validation_v2.json`.

## Interpretación de estados

| Estado | Condición |
| --- | --- |
| Evidencia insuficiente | Poca información base, calidad insuficiente o validación interna insuficiente. |
| Sin pérdida anómala detectada | No cumple conjuntamente tendencia residual, efecto material y persistencia bajo la banda, tras corrección de multiplicidad. No significa lago intacto ni ausencia de pérdida observada. |
| Pérdida no explicada | Hay anomalía según los criterios, pero falta evidencia para atribuirla. |
| Indicios de intervención humana | Además de anomalía, control elegible y comparación diferencial, hay una presión creciente previa y asociación negativa con p ajustados. |
| Evidencia reforzada de intervención | También hay una intervención independiente documentada y revisada, compatible en actividad y fecha. No equivale a certeza causal. |

Ninguna regla asigna automáticamente una causa por aprobar dos de tres pruebas. La descomposición muestra cambio modelado y diferencia de tendencias no atribuida; no publica porcentajes de impacto humano.

Si gana la climatología, la detección se interpreta como cambio frente a una referencia y no habilita atribución humana: una media constante no representa explícitamente los efectos meteorológicos.

## Qué se exige a los controles

Se publica correlación previa, MAE posterior normalizado por la media base y cobertura de banda. La política también exige aprobación documentada independiente: no basta con que el control ajuste bien. El registro comienza vacío; no hay tres controles confirmados por el mero hecho de aparecer como gemelas en la configuración.

En `config/evidence_policy.json`, registrar solo tras verificar fuente y supuestos:

```json
{
  "control_reviews": {
    "ID_VERIFICADO": {
      "approved": true,
      "source": "Referencia independiente de la revisión",
      "reviewer": "Persona responsable"
    }
  },
  "documented_interventions": [
    {
      "body_id": "CASO_VERIFICADO",
      "suspect": "INDICADOR_COMPATIBLE",
      "year": 2005,
      "source": "Documento independiente con fecha y actividad",
      "reviewed": true,
      "human_activity_verified": true
    }
  ]
}
```

Estos son ejemplos de formato, no evidencia de un caso real. Sin fuentes independientes no se calculan accuracy, precisión, recall o F1 de atribución. Los nueve placebos de fecha en controles candidatos son exploratorios, no una tasa confirmada de falsos positivos. Tampoco se declara completada la validación causal de uno o dos lagos: faltan intervenciones verificadas.

## Incertidumbre y dependencia temporal

Las bandas nominales de 80% usan 400 réplicas bootstrap de residuos en bloques de tres años y son aproximadas. Se conserva su cobertura posterior, que puede ser muy baja aunque el MAE sea pequeño. No se declara que las bandas estén calibradas.

Las tendencias se contrastan permutando bloques; la asociación de presión usa cambios anuales y desplazamientos circulares, con signo negativo obligatorio y corrección de Holm. Se corrigen además las pruebas climáticas y de control entre cuerpos. Estos procedimientos son exploratorios, tienen baja potencia con 40 años y no eliminan toda confusión o dependencia. Se necesita sensibilidad a bloques, períodos base y umbrales antes de una evaluación confirmatoria.

Los umbrales de similitud, error, cobertura y efecto en la política son provisionales y ajustables; no son estándares universales. La selección y los intervalos requieren más validación independiente. El R² de entrenamiento no acredita un contrafactual causal.

## Calidad de las fuentes

Los CSV existentes no se reescriben: las banderas inferidas se exportan aparte. `nodata_pct > 20` permite identificar algunas imputaciones de agua heredadas; otras pueden no estar marcadas. Los ceros históricos de presiones se conservan, pero no se certifican como ausencia real.

En futuras extracciones se guardan `water_imputed`, `water_status` y `value_status`; no se prolongan automáticamente niveles fuera de cobertura, ni se rellenan extremos de agua sin dato. Hansen se rellena con cero únicamente dentro de su cobertura anual declarada; los años anteriores quedan ausentes. Los años climáticos requieren doce meses distintos y válidos. Estos cambios de extracción se verificaron por sintaxis; no se llamó Earth Engine ni se descargaron fuentes nuevas.
