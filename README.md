# Detector de huella humana en el agua de Bolivia

NASA Space Apps 2026, reto *Be an Earth System Trend Detective*.
Separa cuánto de la pérdida de un cuerpo de agua explica el clima (sequía, El Niño) y cuánto no,
y audita qué actividad humana es la sospechosa.

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
| `app/app.py` | P3 Interfaz | Entrada de Streamlit: tema, navegación superior y despacho de vistas |
| `app/theme.py`, `app/ui.py` | P3 Interfaz | Paleta, estilos, partículas de fondo; tarjetas y gráficos SVG animados |
| `app/data.py`, `app/nav.py` | P3 Interfaz | Carga de datos con caché; navegación entre vistas |
| `app/views/` | P3 Interfaz | Panorama (tablero y vistas agregadas), Mapa 3D, Monitoreo, Ficha y Vigilancia |
| `app/map3d.py`, `app/icons.py` | P3 Interfaz | Capas del mapa 3D y comparador; iconos Lucide (`app/icons/`, ISC) |
| `gee/extraer_series.py` | P1 Datos | Cómo correr lo mismo desde Google Colab |

## Arranque

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

La app usa `data/real` automáticamente cuando existe `results.json`. Para la capa Landsat en vivo sobre el mapa 3D:

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

## Publicar en la web (Streamlit Community Cloud, gratis)

1. Entrar a https://share.streamlit.io con la cuenta de GitHub y elegir **Create app**.
2. Repositorio `gustavoantequerat-del/Earth-System-Detective`, rama `main`, archivo principal `app/app.py`.
3. En **Advanced settings** elegir Python 3.13 y, si se quiere, pegar los secretos de
   `.streamlit/secrets.toml.example` (Telegram y la cuenta de servicio de Earth Engine).
4. **Deploy**. La app lee los resultados ya calculados de `data/real` y `data/national`, así que funciona sin
   Earth Engine; con la cuenta de servicio se activan las capas en vivo (agua por año, Sentinel-2 reciente, FIRMS).

Enlaces directos para compartir: `?vista=cerca` (fuentes de agua cercanas a quien abre el enlace),
`?vista=ficha&laguna=concepcion`, `?vista=verificacion`, `?vista=mapa`.

## Novedades para el impacto

- **Cerca de mí**: con la ubicación del navegador o un lugar escrito, lista las fuentes de agua del radio elegido,
  de la más grave a la menos, con alertas de incendio, agua artificial y protección legal.
- **Ficha PDF** por laguna: veredicto, motivos, las tres pruebas, sospechosos, protección legal, antes y después
  y fuentes (`app/report.py`).
- **Ramsar y áreas protegidas** (`uma/protected.py`, WDPA): 6 de los 8 cuerpos de agua analizados y 66 de las 300
  lagunas del barrido nacional están en sitios Ramsar.
- **Telegram**: botón de alerta de prueba en Vigilancia.
- **Cómo lo verificamos**: datos contra fuentes independientes, veredictos contra estudios y prensa, límites del
  método y corridas auditadas.
- **Mapa**: modo 2D liviano para celular, imagen Sentinel-2 de los últimos 90 días y caché de capas de 2 horas.

## Aguas arriba y el rio por tramos (`uma/rivers.py`)

El Poopo y Uru Uru no viven de su lluvia: se llenan con el agua que baja del Titicaca por el Desaguadero. Con la
lluvia local el modelo de clima del Poopo no era significativo (p = 0.30) y el lago quedaba incalculable. Ahora el
motor agrega una entrada aguas arriba cuando la laguna recibe agua de otra que drena al menos el 30% de su cuenca:
la superficie del Titicaca para el Poopo y el agua medida en el Desaguadero antes de Uru Uru (tramo T4). Si la
mayor parte de la perdida llega por el rio, el veredicto es **Aguas arriba** y la ficha cita el veredicto de la
fuente.

`uma/rivers.py` sigue el cauce (HydroSHEDS) en tramos T1-T6 mas el Mauri y mide por ano el agua en el cauce, el
verde en epoca seca a 5 km (riego) y las represas, y arma un inventario de OpenStreetMap (canales, tomas, minas,
plantas de tratamiento). Hallazgos: el agua en el cauce a la salida del Titicaca cayo de 5,619 ha (1985) a 126 ha
(2024) mientras el lago perdio el 21% de su superficie: el Desaguadero funciona como un rebalse. El riego junto al
rio crece unas 800 ha (de ~2,070 a ~2,890 ha verdes en la epoca seca, con Landsat 8/9 ajustado), del orden de 5 hm3 por ano frente a los ~1,300 hm3 que el Poopo necesitaria.

Otros ajustes: evaporacion sobre el espejo de los lagos poco profundos (`hydro_extra.py --lake-pet`, ERA5-Land) y
Landsat 8/9 llevado a la escala de 5/7 (Roy et al. 2016) en el verde del rio.

## Asistente con IA (Claude) y explicaciones para todos

- **Explícamelo fácil** (en cada ficha) y la vista **Pregunta**: Claude (`claude-opus-5-5`) explica en lenguaje
  sencillo, en español, quechua, aymara o inglés, usando solo los resultados del detector (`app/ai.py` le pasa el
  veredicto, los motivos, las pruebas, los sospechosos, el río y la protección legal). Debe decir qué tan seguro
  está el detector y no inventar cifras. Botón **Escuchar**: lee la respuesta con la voz del navegador.
- Sin clave, la app muestra una explicación armada con plantillas a partir de los mismos datos.
- Clave: `ANTHROPIC_API_KEY` en `.env` (local) o en los secretos de Streamlit Cloud.

## Cadena aguas arriba: cuánto es humano

Cuando una laguna es "Aguas arriba", la parte humana de lo que deja de llegar se acota con el veredicto de la
fuente: como mucho, la fracción humana de la pérdida de la fuente. Si la fuente tiene confianza baja (hoy el
Titicaca), se informa un rango desde 0. Poopó: de 0 a 87,907 ha de 110,460 ha; Uru Uru: de 0 a 3,739 ha.
