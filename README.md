# Detector de huella humana en el agua de Bolivia

NASA Space Apps 2026, reto *Be an Earth System Trend Detective*.
Compara la evolución del agua con referencias climáticas, detecta anomalías con incertidumbre
y evalúa indicios de presión humana. No asigna automáticamente una causa a un residuo.

La implementación conservadora y sus límites están documentados en [VALIDACION_MODELO.md](VALIDACION_MODELO.md).
Los resultados actuales están en [data/real/validation/REPORT.md](data/real/validation/REPORT.md).

## Arranque del dashboard

Usa Node.js 20.9+, 22 o 24 y npm. Desde la carpeta raíz instala las dependencias y compila el frontend:

```bash
npm ci
npm run build
```

En una terminal inicia NestJS en el puerto 3001:

```bash
npm run start:dev
```

En otra terminal inicia Next.js y abre [localhost:3000](http://localhost:3000):

```bash
npm run start
```

Para editar el frontend con recarga automática, usa `npm run dev:frontend`. Los dos servidores arrancan con Node.js
y NestJS carga los datos procesados que incluye el repositorio. Los scripts científicos de Python se ejecutan aparte
para descargar nuevas series, recalcular los diagnósticos, generar el barrido y actualizar los reportes de incendios.

La barra superior lleva a **Panorama**, **Mapa 3D**, **Monitoreo**, **Fichas** e **Incendios**.
En el mapa, usa **Balance hídrico** para explorar el barrido nacional y **Modelo conservador** para consultar
los resultados de `mapa3`. El método y el cuerpo de agua seleccionado quedan en la URL. Puedes abrir directamente
el [mapa con el modelo conservador](http://localhost:3000/?vista=mapa&metodo=conservador).

### Vercel

Importa el repositorio con el preset **Services** y la **raíz del repo** como Root Directory. Selecciona
`developer` como rama de producción. El `vercel.json` de la raíz dirige `/api/*` a NestJS y las páginas a
Next.js en el mismo dominio. Los datos precalculados y las imágenes se incluyen en el backend, por lo que la
demo arranca con Node.js. Deja `BACKEND_URL` sin definir para usar el enrutamiento del proyecto.

La auditoría de la demo es de solo lectura. El archivo SQLite empaquetado permite consultar el historial.
Para agregar revisiones en Vercel hace falta una base persistente. Las capas en vivo de Earth Engine se
habilitan al configurar `GEE_SERVICE_ACCOUNT_KEY` y, si corresponde, `UMA_GEE_PROJECT`.

Inicio muestra alertas calculadas a partir de los archivos de agua y pérdida de bosque. Las alertas de
FIRMS proceden del reporte guardado y los simulacros se identifican como tales. En las fichas, **NASA
reciente** consulta NASA POWER y el catálogo Earthdata CMR sin clave. Con acceso de Earth Engine se puede
comparar el mismo mes con GPM IMERG, CHIRPS y ERA5-Land. Configura `FIRMS_MAP_KEY` en el entorno del
backend para activar las detecciones de VIIRS NOAA-20 cerca de los lagos. Las claves se guardan en
variables de entorno de NestJS y Vercel.

**Incendios** reproduce los 312 meses del mapa MODIS de `mapa3` con barras 3D, escala de color fija,
control de velocidad y pausa. **Vegetación → Por provincia** integra el mapa, los diagnósticos de
lluvia y NDVI y la serie temporal de `vegetacion-agua`. La vista **Cuencas de lagos** mantiene sus
propias series e imágenes. Los archivos originales de esa rama viven en `Naseros/`.

El atlas se prepara sin cambiar el análisis original. Para regenerar el archivo comprimido tras
actualizar sus CSV, instala las dependencias científicas de `Naseros/requirements.txt` y ejecuta
`python backend/scripts/export-regional-vegetation.py`. El servicio desplegado lee el archivo
precalculado desde NestJS.

### Configuración local

- **NestJS** (`backend/`) sirve diagnósticos, series de agua, imágenes, vigilancia e historial y guarda las
  revisiones en el archivo `uma.db` existente. Usa `data/real` si contiene resultados, con `data/sample` como respaldo.
  Define `UMA_DATA` en `.env` para usar otra carpeta de datos. El barrido nacional y sus puntos de agua artificial
  aparecen si se generan `data/national/results.json` y `data/national/agua_artificial.json`, respectivamente.
- **Next.js** (`frontend/`) reenvía `/api` a NestJS. Si cambias el puerto del backend, configura
  `BACKEND_URL=http://127.0.0.1:<puerto>` en `frontend/.env.local` y recompila Next.js.
- **Mapa en vivo**. Copia `.env.example` a `.env` y configura `GOOGLE_APPLICATION_CREDENTIALS` con la ruta de un
  archivo JSON de una cuenta de servicio con acceso a Earth Engine. También puedes usar `GEE_SERVICE_ACCOUNT_KEY`
  con el contenido de ese JSON. `UMA_GEE_PROJECT` permite elegir otro proyecto. Con esta configuración aparecen los
  modos Landsat y MapBiomas y la capa de incendios FIRMS. El mapa satelital de Esri y el relieve de AWS usan sus
  servicios públicos.

## Estructura

| Carpeta | Quién | Qué |
|---|---|---|
| `uma/upstream.py` | P1 Datos | Cuenca de aporte completa de cada cuerpo de agua (HydroBASINS) |
| `uma/nasa_power.py` | P1 Datos | Clima NASA POWER promediado en la cuenca de aporte (sin clave) |
| `uma/gee_extract.py` | P1 Datos | Earth Engine: agua Landsat, validación JRC, sospechosos, imágenes antes/después |
| `uma/suspects_upstream.py` | P1 Datos | Sospechosos medidos en la cuenca de aporte (misma área que el clima) |
| `uma/context.py` | P1 Datos | Alrededores: mapa de lo que apareció (MapBiomas, Hansen) y lugares de OpenStreetMap |
| `uma/twins.py` | P2 Modelo | Búsqueda de gemelas de control (gHM, áreas protegidas, otra cuenca) |
| `uma/national.py` | P2 Modelo | Barrido nacional: detecta las lagunas de Bolivia y les aplica un diagnóstico rápido |
| `uma/alerts.py` | Operación | Vigilancia semanal de incendios (NASA FIRMS) con aviso por Telegram o correo |
| `uma/hindcast.py` | P2 Modelo | Prueba hacia atrás: qué tan predictivo es el sistema |
| `.github/workflows/alertas.yml` | Operación | Corre la vigilancia cada lunes en GitHub Actions |
| `uma/engine.py` | P2 Modelo | Motor: tendencia, 3 pruebas, confianza, descomposición, sospechosos, estado, calidad |
| `uma/audit.py` | P2 Modelo | Auditoría en SQLite (`data/real/uma.db`): corridas, veredictos, alertas, revisiones |
| `uma/synthetic.py` | P2/P3 | Datos de prueba ficticios con el mismo formato |
| `run_engine.py` | P2 | CSV → `results.json` + registro de auditoría |
| `frontend/` | P3 Interfaz | Next.js: panorama, mapa 3D, alertas, ficha, antes/después, alrededores, historial |
| `backend/` | API | NestJS: acceso a datos locales, imágenes, auditoría SQLite y capas de Earth Engine |
| `app/` | P3 Interfaz original | Dashboard Streamlit con tema, vistas agregadas y mapa 3D |
| `gee/extraer_series.py` | P1 Datos | Cómo correr lo mismo desde Google Colab |

## Arranque de la interfaz original

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python run_engine.py
.venv\Scripts\streamlit run app/app.py
```

## Datos de NASA

| Uso en el detector | Dataset NASA | Acceso | Estado |
|---|---|---|---|
| Lluvia y temperatura por laguna, 1985-2024 | NASA POWER (PRECTOTCORR, T2M de MERRA-2) | API sin clave: `python -m uma.nasa_power` | Extraído en `data/real/nasa_power.csv` |
| Superficie de agua, 1985-2024 | Landsat 5/7/8/9 C2 L2 (NASA/USGS), MNDWI en época seca | Earth Engine `LANDSAT/L*0*/C02/T1_L2` | Requiere proyecto GEE |
| Imágenes antes/después y capa en vivo | Landsat 5/7/8/9 | Earth Engine | Requiere proyecto GEE |
| Incendios por año en la cuenca | MODIS MCD64A1 | Earth Engine `MODIS/061/MCD64A1` | Requiere proyecto GEE |
| Focos de calor, casi tiempo real | FIRMS (MODIS y VIIRS) | Earth Engine `FIRMS` | Capa en vivo del mapa 3D |
| Riego (verde en época seca) | Landsat NDVI | Earth Engine | Requiere proyecto GEE |

Fuentes externas para validar y para lo que NASA no cubre: JRC Global Surface Water (validación del agua,
hasta 2021), Hansen GFC 2025 (desmonte, derivado de Landsat), MapBiomas Bolivia colección 2 (minería, ciudad,
agricultura, pasto), DMSP-OLS + VIIRS (luces), WorldPop (población), GRACE (agua subterránea, contexto),
HydroBASINS (cuencas), ONI de NOAA
(El Niño, extraído en `data/real/oni.csv`). Con `--climate chirps` se usa CHIRPS + ERA5-Land en lugar de NASA POWER.

Todos los IDs de Earth Engine se verificaron en el catálogo público el 2026-11-14.

## Enlaces para el equipo

**Imágenes NASA en tiempo real y antes/después (sin programar)**

- [NASA Worldview](https://worldview.earthdata.nasa.gov): imágenes diarias MODIS y VIIRS casi en tiempo real; el modo
  *Compare* pone dos fechas lado a lado con deslizador (antes/después).
- [FIRMS, mapa de incendios](https://firms.modaps.eosdis.nasa.gov/map/): focos de calor de las últimas horas.
  [Clave de la API](https://firms.modaps.eosdis.nasa.gov/api/) · [Ficha en Earthdata](https://www.earthdata.nasa.gov/data/tools/firms)
- [LandsatLook (USGS)](https://landsatlook.usgs.gov): todas las escenas Landsat desde 1972, para elegir el antes y el después.
- [EarthExplorer (USGS)](https://earthexplorer.usgs.gov): descarga de escenas Landsat completas.
- [Earthdata Search](https://search.earthdata.nasa.gov): buscador de todos los datos NASA ([cuenta Earthdata](https://urs.earthdata.nasa.gov)).
- [NASA GIBS](https://nasa-gibs.github.io/gibs-api-docs/): las mismas capas de Worldview como teselas para un mapa web.
- [OPERA DSWx](https://www.earthdata.nasa.gov/data/projects/opera): agua superficial casi en tiempo real (Landsat y Sentinel, desde 2023).
- [HLS](https://www.earthdata.nasa.gov/data/projects/hls): Landsat + Sentinel-2 armonizados, una imagen cada 2-3 días.

**Datasets que usa el detector (ficha en el catálogo de Earth Engine)**

| Uso | Dataset | Enlace |
|---|---|---|
| Agua, imágenes antes/después, capa en vivo | Landsat 5 | [LANDSAT/LT05/C02/T1_L2](https://developers.google.com/earth-engine/datasets/catalog/LANDSAT_LT05_C02_T1_L2) |
| | Landsat 7 | [LANDSAT/LE07/C02/T1_L2](https://developers.google.com/earth-engine/datasets/catalog/LANDSAT_LE07_C02_T1_L2) |
| | Landsat 8 | [LANDSAT/LC08/C02/T1_L2](https://developers.google.com/earth-engine/datasets/catalog/LANDSAT_LC08_C02_T1_L2) |
| | Landsat 9 | [LANDSAT/LC09/C02/T1_L2](https://developers.google.com/earth-engine/datasets/catalog/LANDSAT_LC09_C02_T1_L2) |
| Imágenes densas (opcional) | HLS Landsat / Sentinel | [HLSL30](https://developers.google.com/earth-engine/datasets/catalog/NASA_HLS_HLSL30_v002) · [HLSS30](https://developers.google.com/earth-engine/datasets/catalog/NASA_HLS_HLSS30_v002) |
| Focos de calor en vivo | FIRMS | [FIRMS](https://developers.google.com/earth-engine/datasets/catalog/FIRMS) |
| Incendios por año | MODIS MCD64A1 | [MODIS/061/MCD64A1](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MCD64A1) |
| Lluvia y temperatura | NASA POWER | [Visor](https://power.larc.nasa.gov/data-access-viewer/) · [API](https://power.larc.nasa.gov/docs/services/api/) |
| Validación del agua | JRC Global Surface Water | [YearlyHistory](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_4_YearlyHistory) · [visor](https://global-surface-water.appspot.com) |
| Desmonte | Hansen GFC 2025 | [catálogo](https://developers.google.com/earth-engine/datasets/catalog/UMD_hansen_global_forest_change_2025_v1_13) · [visor](https://glad.earthengine.app/view/global-forest-change) |
| Minería, ciudad, agricultura, pasto | MapBiomas Bolivia colección 2 | [bolivia.mapbiomas.org](https://bolivia.mapbiomas.org) (asset público en Earth Engine) |
| Luces nocturnas | DMSP-OLS y VIIRS anual | [DMSP](https://developers.google.com/earth-engine/datasets/catalog/NOAA_DMSP-OLS_NIGHTTIME_LIGHTS) · [VIIRS](https://developers.google.com/earth-engine/datasets/catalog/NOAA_VIIRS_DNB_ANNUAL_V22) |
| Población | WorldPop | [catálogo](https://developers.google.com/earth-engine/datasets/catalog/WorldPop_GP_100m_pop) |
| Agua subterránea | GRACE / GRACE-FO (NASA) | [catálogo](https://developers.google.com/earth-engine/datasets/catalog/NASA_GRACE_MASS_GRIDS_V04_MASCON) |
| Cuencas | HydroBASINS | [catálogo](https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_v1_Basins_hybas_8) · [HydroSHEDS](https://www.hydrosheds.org/products/hydrobasins) |
| Relieve (opcional) | NASADEM | [NASA/NASADEM_HGT/001](https://developers.google.com/earth-engine/datasets/catalog/NASA_NASADEM_HGT_001) |
| El Niño | ONI de NOAA | [tabla](https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/ensostuff/ONI_v5.php) · [texto](https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt) |
| Para programar | Earth Engine Code Editor | [code.earthengine.google.com](https://code.earthengine.google.com) |

## Datos reales (Earth Engine)

1. Registrar un proyecto en https://code.earthengine.google.com/register (uso no comercial).
2. Autenticar una vez: `.venv\Scripts\earthengine authenticate`
3. Revisar `config/bodies.csv` (cuerpos de agua, radio y gemela de control).
4. Extraer todo a `data/real/` (series, sospechosos, imágenes Landsat antes/después, ONI):

```bash
.venv\Scripts\python -m uma.gee_extract --project TU-PROYECTO
.venv\Scripts\python run_engine.py data/real 2000
```

5. Revisar `data/real/check.csv`: si la superficie máxima de agua de un área es 0 o absurda, corregir las
   coordenadas o el radio en `config/bodies.csv` y volver a correr con `--only <body_id>`.

La app usa `data/real` automáticamente cuando existe `results.json`. Para la capa Landsat en vivo en la interfaz original de Streamlit:

```bash
set UMA_GEE_PROJECT=TU-PROYECTO && .venv\Scripts\streamlit run app/app.py
```

## Mapa 3D

Relieve real (AWS Terrain Tiles) con imagen satelital (Esri) o, con Earth Engine activo, el Landsat de época seca
del año elegido con el agua JRC encima, generado en vivo. Cada cuerpo de agua es una columna: color = estado,
altura = % de agua perdida. Clic en una columna → el mapa vuela hasta ahí y abajo aparece la tarjeta con el
comparador antes/después.

## Contrato de datos (P1 → P2)

`bodies.csv`: `body_id, name, lat, lon, kind, control_id, department`
(`control_id` = body_id de la gemela; vacío en las gemelas.)

`series.csv`: `body_id, year, water_ha, precip_mm, temp_c, oni` (una fila por año, sin huecos)

`suspects.csv`: `body_id, year, suspect, value[, area]`. Nombres de `suspect` reconocidos:
`forest_loss_ha, burned_ha, dry_crop_ha, mining_ha, urban_ha, pasture_ha, agri_ha, night_lights, population,
artificial_water_ha`. `area` dice si se midió en la `cuenca_aporte` o en la `subcuenca_local`.

## Cómo decide el motor

### Balance hídrico

1. **Prueba 1, clima.** Modelo `agua ~ lluvia + lluvia(t-1) + temperatura + ONI` entrenado solo en el periodo base
   (por defecto hasta 2000). Pasa si el residuo cae de forma significativa (Mann-Kendall p < 0.05) y en más de 10%
   de la media base.
2. **Prueba 2, control.** Pasa si el residuo, en % de la media base, cae más que el de la gemela (Mann-Kendall
   sobre la diferencia).
3. **Prueba 3, coincidencia.** Pasa si el sospechoso principal crece de forma significativa, empieza a crecer
   0 a 5 años antes del quiebre del residuo (Pettitt) y se correlaciona negativamente con él (más presión, menos agua).

Confianza: 3 pruebas = alta, 2 = media, 0 o 1 = baja. Si la serie de agua es de calidad baja (Landsat vs JRC
r < 0.7), la confianza baja un nivel y la app lo advierte.

Descomposición: cambio entre el promedio del periodo base y el de los últimos 5 años (el mismo % de la tarjeta),
repartido en sequía y calor, El Niño, huella humana (solo con 2 o más pruebas) y sin explicar. Las partes suman el total.

Estados: **Huella humana** (un sospechoso directo pasa la prueba de coincidencia y al menos otra prueba pasa),
**Causa climática** (cae al menos 10%, el modelo de clima es confiable y explica al menos el 60%), **Alerta temprana**
(presión de uso del suelo creciendo y agua aún estable), **Incalculable** (el agua cae pero con los datos disponibles
no se puede calcular la causa con confianza; cada laguna lista sus motivos) e **Intacto**.

Modelo de clima: agua ~ balance de dos años (anomalía de lluvia menos anomalía de evaporación potencial de ERA5-Land)
+ El Niño, entrenado en 1985-2000. Es confiable si es significativo (p < 0.05) y si más balance da más agua; si no,
la prueba del clima queda "no evaluable" y las otras usan el agua observada (la gemela controla el clima).
La gemela solo vale si su propia agua cambió menos de 25%. Población, luces nocturnas y ciudad de toda la cuenca son
indicadores indirectos: se muestran, pero no pueden ser el culpable. Pérdidas de 10-15% dan confianza baja.
Sospechosos nuevos: agua consumida por cultivos en época seca (MODIS MOD16, NASA) y déficit de agua en el cauce del
Desaguadero respecto de lo esperado por el nivel del Titicaca y la lluvia (`uma/hydro_extra.py`).

Áreas: el agua se mide en el círculo de la laguna; el clima, en la cuenca de aporte completa; los sospechosos, en dos
escalas que se auditan por separado: "cerca" (subcuenca local) y "cuenca" (cuenca de aporte completa)
(`uma/suspects_upstream.py`). MapBiomas solo cubre la parte boliviana de cada cuenca.

Limitación: prueba coincidencia y consistencia, no causalidad estricta.

## Agua artificial y tendencias opuestas

MapBiomas Agua Bolivia (colección 4, 1985-2025) clasifica cada cuerpo de agua. Los códigos se dedujeron en sitios
conocidos: 11 natural, 22 represa o reservorio (Misicuni), 23 otra agua artificial (estanques), 24 poza minera
(Tipuani). El detector usa `artificial_water_ha` (21-23) y `mining_water_ha` (24) como sospechosos, cerca y en la cuenca,
y muestra en la tarjeta el agua natural contra la artificial.

## Barrido nacional

```bash
.venv\Scripts\python -m uma.national --project TU-PROYECTO --max 300
```

Detecta lagunas (agua natural de MapBiomas Agua en al menos 25% de los años, al menos 100 ha, forma compacta para
descartar ríos), baja el agua por año, el uso humano del suelo en un anillo de 5 km y el clima NASA POWER, y aplica
el motor con una gemela regional sintética (mediana de lagunas con poca presión de la misma celda de 3 grados).
Resultado en `data/national/`; la app lo muestra como capa del mapa 3D. Es un filtro para elegir dónde hacer el
análisis completo, no un veredicto final.

## Vigilancia semanal de incendios

```bash
.venv\Scripts\python -m uma.alerts --project TU-PROYECTO --dry-run   # revisar sin avisar
.venv\Scripts\python -m uma.alerts --project TU-PROYECTO             # revisar y avisar
```

Cuenta focos de calor NASA FIRMS de los últimos 7 días cerca y en la cuenca de cada cuerpo de agua vigilado, y
avisa si un cuerpo de agua en riesgo tiene al menos 5 focos y el doble de lo normal para esa semana (promedio de
los 5 años anteriores). Para avisos, copiar `.env.example` como `.env` y completar Telegram o correo. Para que
corra solo cada lunes: `.github/workflows/alertas.yml` (requiere una cuenta de servicio de Earth Engine guardada
como secreto `GEE_SERVICE_ACCOUNT_KEY` en GitHub). Prueba retroactiva: con la semana al 2019-08-25 avisa en la
laguna de la Chiquitanía este (163 focos cerca contra 1.2 normales).

## Verificación cruzada (`uma/verify.py`)

Compara los datos del sistema con fuentes que el motor no usa: agua de Landsat contra MapBiomas Agua (r de 0.86 a
0.98 en las lagunas bolivianas) y lluvia de NASA POWER contra CHIRPS (r de 0.53 a 0.77). Coinciden con hechos
publicados: la Laguna Concepción seca en 2003-2005 y 2021-2022, el mínimo del Titicaca en 2023-2024 y Pozuelos
casi seca en 1994-1996. Como las dos fuentes de lluvia discrepan, `uma/climate_blend.py` usa su promedio
(`precip_mm`) y guarda ambas (`precip_power_mm`, `precip_chirps_mm`).

Reglas de evidencia de los sospechosos: un sospechoso medido en hectáreas tiene que crecer al menos el 10% del agua
perdida (si no, queda como débil), y "antecede la caída" si ya había crecido 1.5 veces alrededor del quiebre del agua.
## Modelo conservador

1. **Calidad y validación.** Excluye agua imputada del ajuste y compara climatología, OLS, Ridge y regresión con memoria residual AR(1), usando solo cortes dentro del período base. Si la calidad o la validación son insuficientes, lo comunica.
2. **Anomalía.** Contrasta tendencia residual y efecto material, exige persistencia bajo una banda bootstrap aproximada y corrige los contrastes entre cuerpos de agua. Publica la cobertura posterior de las bandas.
3. **Control.** Una gemela es candidata hasta documentar su elegibilidad independiente. Se revisan similitud previa, error y cobertura; si falla, su prueba no se habilita.
4. **Presión.** Exige crecimiento, antecedencia y signo negativo en la asociación de cambios anuales, con corrección de Holm y contrastes temporales exploratorios.
5. **Conclusión.** No basta con aprobar dos pruebas. Hay estados de evidencia insuficiente, pérdida no explicada e indicios; la evidencia reforzada exige documentación independiente revisada. La diferencia de tendencias no se reparte numéricamente como causa humana.

La política está en `config/evidence_policy.json`; sus umbrales son provisionales y configurables. Las revisiones de controles y los eventos documentados comienzan vacíos: no se inventan confirmaciones. Los placebos en controles candidatos son exploratorios y no constituyen una tasa confirmada de falsos positivos. No hay métricas de clasificación humana contra etiquetas independientes disponibles.

La evaluación posterior usa clima observado: es retrospectiva y condicional, no un pronóstico operativo de lluvia. Las bandas no se declaran calibradas. La documentación detalla qué datos y revisiones faltan para una atribución confirmatoria.
En Next.js, selecciona **Modelo conservador** para ver los resultados, bandas, pruebas y auditoría de este método.
El barrido nacional publicado corresponde al método de balance hídrico. Para generar nuevas corridas
conservadoras con las entradas actuales, ejecuta `python run_engine.py data/real 2000 --conservative`.
Se guardan en `data/real/validation/`, con su propio JSON, auditoría y tablas de validación.
Consulta [la metodología conservadora y sus límites](VALIDACION_MODELO.md).
