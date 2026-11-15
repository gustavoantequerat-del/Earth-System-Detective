'use client';

import { useEffect, useId, useState } from 'react';
import { ArrowUpRight, CalendarDays, CloudRain, Flame, Satellite } from 'lucide-react';
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api, displayDate, number, signed, type BodyDetail, type ClimateYear } from './data';
import { DataTable } from './ui';

const climateMetrics = {
  rain: { label: 'Lluvia', unit: 'mm', note: 'Dos estimaciones independientes de lluvia anual en la zona. Úsalas para comprobar si coinciden los años más secos o lluviosos.',
    lines: [{ key: 'powerMm', label: 'NASA POWER', color: '#7caeff' }, { key: 'chirpsMm', label: 'CHIRPS', color: '#91e9d2' }] },
  temp: { label: 'Temperatura', unit: '°C', note: 'Temperatura media anual utilizada en el archivo del proyecto.',
    lines: [{ key: 'tempC', label: 'Temperatura media', color: '#ffb17e' }] },
  balance: { label: 'Lluvia y evaporación potencial', unit: 'mm', note: 'La evaporación potencial aproxima cuánta agua podría perderse por evaporación. Es una estimación climática.',
    lines: [{ key: 'rainMm', label: 'Lluvia usada por el modelo', color: '#7caeff' }, { key: 'petMm', label: 'Evaporación potencial', color: '#ffb17e' }] },
  water: { label: 'Superficie observada', unit: 'ha', note: 'Landsat y JRC estiman superficie de agua con métodos distintos. Se pueden comparar las tendencias en los años donde hay datos de ambos.',
    lines: [{ key: 'waterHa', label: 'Landsat', color: '#8bbdff' }, { key: 'jrcHa', label: 'JRC Global Surface Water', color: '#b5ef8a' }] },
  storage: { label: 'Agua almacenada (GRACE)', unit: 'cm', note: 'GRACE mide cambios en el almacenamiento total de agua a escala regional. El valor es una anomalía respecto a la referencia del producto.',
    lines: [{ key: 'storageCm', label: 'Anomalía de almacenamiento', color: '#82dcff' }] },
  oni: { label: 'El Niño y La Niña', unit: '°C', note: 'El índice ONI de NOAA resume la temperatura superficial del Pacífico ecuatorial. Sirve como contexto climático para la serie del lago.',
    lines: [{ key: 'oni', label: 'Índice ONI', color: '#ffc385' }] },
} as const;
type ClimateMetric = keyof typeof climateMetrics;

function valueText(value: number | null | undefined, unit: string) {
  return value == null ? '—' : `${number(value, 1)} ${unit}`;
}

export function ClimateArchive({ detail }: { detail: BodyDetail }) {
  const [metric, setMetric] = useState<ClimateMetric>('rain');
  const rows = detail.climate ?? [];
  const selected = climateMetrics[metric];
  const last = rows.at(-1);
  return <section className="environment-panel" aria-labelledby="climate-archive-title">
    <div className="mission-chart-heading">
      <div><h3 id="climate-archive-title">Qué se midió cada año</h3><p>{selected.note}</p></div>
      <label><span id="climate-archive-label">Indicador</span>
        <select aria-labelledby="climate-archive-label" value={metric} onChange={(event) => setMetric(event.target.value as ClimateMetric)}>
          {Object.entries(climateMetrics).map(([key, item]) => <option key={key} value={key}>{item.label}</option>)}
        </select></label>
    </div>
    {rows.some((row) => selected.lines.some(({ key }) => row[key] != null)) ? <>
      <div className="environment-chart">
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <LineChart data={rows} margin={{ top: 15, right: 15, left: 5, bottom: 0 }}>
            <CartesianGrid stroke="#314c79" vertical={false} />
            <XAxis dataKey="year" stroke="#bfcee9" minTickGap={26} />
            <YAxis width={65} stroke="#bfcee9" unit={` ${selected.unit}`} domain={['auto', 'auto']} />
            <Legend />
            <Tooltip contentStyle={{ background: '#112145', border: '1px solid #496489', borderRadius: 12 }}
              formatter={(value) => typeof value === 'number' ? valueText(value, selected.unit) : 'Sin medición'} />
            {selected.lines.map(({ key, label, color }) => <Line key={key} type="linear" dataKey={key} name={label} stroke={color}
              strokeWidth={3} dot={false} isAnimationActive={false} />)}
          </LineChart>
        </ResponsiveContainer>
      </div>
      {last?.missingPct != null && metric === 'water' && <p className="muted">Cobertura del último año Landsat: {number(100 - last.missingPct, 1)} % de píxeles con dato.</p>}
      <details className="mission-table-expand"><summary>Ver mediciones por año</summary>
        <DataTable rows={rows.map((row: ClimateYear) => ({
          Año: row.year, ...Object.fromEntries(selected.lines.map(({ key, label }) => [label, valueText(row[key], selected.unit)])),
        }))} />
      </details>
    </> : <p className="notice">El archivo de este lago no contiene mediciones para el indicador seleccionado.</p>}
    {detail.catchment && <p className="environment-catchment"><strong>Cuenca de aporte · HydroBASINS</strong>
      {detail.catchment.areaKm2 != null && ` ${number(detail.catchment.areaKm2)} km² de superficie`}
      {detail.catchment.subbasins != null && ` · ${number(detail.catchment.subbasins)} subcuencas`}</p>}
  </section>;
}

type DataState = 'available' | 'empty' | 'unavailable' | 'not_configured';
type Month = { date: string; rainMm: number | null; tempC: number | null; rainNormalMm: number | null; tempNormalC: number | null };
interface NasaResponse {
  power: { status: DataState; source: string; reference: [number, number]; months: Month[] };
  catalog: { id: string; name: string; purpose: string; earthdata: string; status: DataState;
    granule: { date?: string; title: string; cloudPct: number | null } | null }[];
  earthEngine: boolean;
}
type Catalog = NasaResponse['catalog'];
interface EarthComparison {
  status: DataState;
  month: string;
  radiusKm: number;
  values: { gpmMm: number | null; chirpsMm: number | null; eraRainMm: number | null; eraTempC: number | null } | null;
}
interface RecentFiresData {
  status: DataState; source: string; days: number; radiusKm: number;
  lastDetection: string | null; lakes: { id: string; name: string; count: number; lastDetection: string | null }[];
}

function CatalogList({ entries }: { entries: Catalog }) {
  return <div className="satellite-list">
    {entries.map(({ id, name, purpose, status, granule, earthdata }) => <article key={id}>
      <div><strong>{name}</strong><p>{purpose}</p></div>
      <div>{granule?.date ? <><time dateTime={granule.date}>{displayDate(granule.date)}</time>
        {granule.cloudPct != null && <small>{number(granule.cloudPct, 1)} % de nubes en la escena</small>}</>
        : <small>{status === 'empty' ? 'Sin archivos en esta zona' : 'Catálogo no disponible'}</small>}</div>
      <a href={earthdata} target="_blank" rel="noreferrer" aria-label={`Abrir ${name} en Earthdata`}><ArrowUpRight size={17} aria-hidden="true" /></a>
    </article>)}
  </div>;
}

export function NasaObservations({ id }: { id: string }) {
  const [response, setResponse] = useState<NasaResponse>();
  const [comparison, setComparison] = useState<EarthComparison>();
  const [attempt, setAttempt] = useState(0);
  const [error, setError] = useState(false);
  const [month, setMonth] = useState('');
  const [pending, setPending] = useState(false);
  const [more, setMore] = useState(false);
  const [extra, setExtra] = useState<Catalog>();
  const [extraError, setExtraError] = useState(false);
  const [extraAttempt, setExtraAttempt] = useState(0);
  const selectId = useId();

  useEffect(() => {
    const request = new AbortController();
    api<NasaResponse>(`bodies/${encodeURIComponent(id)}/nasa`, { signal: request.signal }).then(setResponse)
      .catch(() => { if (!request.signal.aborted) setError(true); });
    return () => request.abort();
  }, [id, attempt]);

  useEffect(() => {
    if (!more || extra) return;
    const request = new AbortController();
    api<Catalog>(`bodies/${encodeURIComponent(id)}/nasa/catalog`, { signal: request.signal }).then(setExtra)
      .catch(() => { if (!request.signal.aborted) setExtraError(true); });
    return () => request.abort();
  }, [id, more, extra, extraAttempt]);

  const power = response?.power;
  const chosen = power?.months.find((row) => row.date === month) ?? power?.months.at(-1);
  const selectedMonth = chosen?.date ?? '';
  const values = comparison?.month === selectedMonth ? comparison?.values : null;
  const delta = (value: number | null, usual: number | null, unit: string) => value == null || usual == null
    ? 'Sin referencia comparable' : `${signed(value - usual, 1)} ${unit} frente a lo habitual`;

  useEffect(() => {
    if (!pending || !selectedMonth) return;
    const request = new AbortController();
    api<EarthComparison>(`bodies/${encodeURIComponent(id)}/climate?month=${encodeURIComponent(selectedMonth)}`, { signal: request.signal })
      .then(setComparison).catch(() => {
        if (!request.signal.aborted) setComparison({ month: selectedMonth, status: 'unavailable', radiusKm: 20, values: null });
      }).finally(() => { if (!request.signal.aborted) setPending(false); });
    return () => request.abort();
  }, [id, selectedMonth, pending]);

  if (error) return <div className="notice danger" role="alert">No pudimos consultar las fuentes de NASA.
    <button type="button" onClick={() => { setError(false); setAttempt((n) => n + 1); }}>Reintentar</button></div>;
  if (!response) return <p className="loading" role="status">Consultando NASA POWER y Earthdata…</p>;
  return <div className="environment-stack">
    <section className="environment-panel" aria-labelledby="nasa-power-title">
      <div className="mission-chart-heading">
        <div><p className="mission-eyebrow"><CloudRain size={16} aria-hidden="true" /> NASA POWER · MERRA-2</p>
          <h3 id="nasa-power-title">Lluvia y temperatura recientes</h3>
          <p>Datos de la cuadrícula que contiene el punto del lago. La referencia compara el mismo mes de 1991 a 2020.</p></div>
        {!!chosen && <label htmlFor={selectId}><span id={selectId + '-label'}><CalendarDays size={16} aria-hidden="true" /> Mes</span>
          <select id={selectId} aria-labelledby={selectId + '-label'} value={selectedMonth} onChange={(event) => {
            setPending(false);
            setMonth(event.target.value);
            setComparison(undefined);
          }}>
            {power?.months.toReversed().map((row) => <option key={row.date} value={row.date}>{displayDate(row.date, false)}</option>)}
          </select></label>}
      </div>
      {chosen ? <>
        <div className="environment-metrics">
          <div><span>Lluvia acumulada del mes</span><strong>{valueText(chosen.rainMm, 'mm')}</strong><small>{delta(chosen.rainMm, chosen.rainNormalMm, 'mm')}</small></div>
          <div><span>Temperatura media del mes</span><strong>{valueText(chosen.tempC, '°C')}</strong><small>{delta(chosen.tempC, chosen.tempNormalC, '°C')}</small></div>
        </div>
        {response.earthEngine ? <div className="environment-compare">
          <button type="button" disabled={pending} onClick={() => setPending(true)}>{pending ? 'Consultando…' : 'Contrastar con GPM, CHIRPS y ERA5-Land'}</button>
          {values ? <DataTable rows={[{ 'Lluvia GPM': valueText(values.gpmMm, 'mm'), 'Lluvia CHIRPS': valueText(values.chirpsMm, 'mm'),
            'Lluvia ERA5-Land': valueText(values.eraRainMm, 'mm'), 'Temperatura ERA5-Land': valueText(values.eraTempC, '°C') }]} />
            : comparison && <p role="status">Earth Engine no devolvió mediciones para el mes.</p>}
          {values && <p className="muted">Promedios espaciales dentro de {comparison?.radiusKm} km del punto. Cada producto tiene su propia resolución y fecha de publicación.</p>}
        </div> : <p className="muted">El contraste mensual de GPM, CHIRPS y ERA5-Land se activa con una cuenta de servicio de Earth Engine.</p>}
      </> : <p className="notice">{power?.status === 'unavailable' ? 'NASA POWER no respondió. El archivo anual de la ficha sigue disponible en Clima y causas.' : 'NASA POWER no devolvió meses completos con datos.'}</p>}
    </section>
    <section className="environment-panel" aria-labelledby="earthdata-title">
      <p className="mission-eyebrow"><Satellite size={16} aria-hidden="true" /> NASA Earthdata · CMR</p>
      <h3 id="earthdata-title">Últimos archivos satelitales disponibles</h3>
      <p>Archivos que intersectan la zona de búsqueda del lago. La fecha indica una escena catalogada. Comprueba su cobertura y nubes antes de usarla como evidencia.</p>
      <CatalogList entries={response.catalog} />
      <details className="mission-table-expand" onToggle={(event) => setMore(event.currentTarget.open)}>
        <summary>Consultar más misiones y modelos</summary>
        <p>Estas consultas verifican qué archivos figuran en el catálogo. Para comparar mediciones hace falta procesar el producto correspondiente.</p>
        {extra ? <CatalogList entries={extra} /> : extraError ? <div className="notice danger" role="alert">No se pudo consultar el catálogo ampliado.
          <button type="button" onClick={() => { setExtraError(false); setExtraAttempt((value) => value + 1); }}>Reintentar</button></div>
          : more && <p className="loading" role="status">Buscando archivos de MODIS, VIIRS, AIRS, OMI, SMAP, GLDAS y MERRA-2…</p>}
      </details>
    </section>
  </div>;
}

export function RecentFires() {
  const [data, setData] = useState<RecentFiresData>();
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const request = new AbortController();
    api<RecentFiresData>('fires/recent', { signal: request.signal }).then(setData)
      .catch(() => { if (!request.signal.aborted) setFailed(true); });
    return () => request.abort();
  }, []);
  return <section className="panel mission-data-panel" aria-labelledby="recent-fires-title">
    <p className="mission-eyebrow"><Flame size={17} aria-hidden="true" /> NASA FIRMS</p>
    <h2 id="recent-fires-title">Focos recientes cerca de los lagos</h2>
    {data?.status === 'available' ? <>
      <p>Detecciones de VIIRS NOAA-20 de los últimos {data.days} días en un radio de {data.radiusKm} km del centro de cada lago.
        Una detección puede corresponder al mismo incendio que otra.</p>
      <DataTable rows={data.lakes.map((lake) => ({ Lago: lake.name, 'Focos detectados': lake.count,
        'Última detección': lake.lastDetection ? displayDate(lake.lastDetection) : '—' }))} />
    </> : <p className="muted" role="status">{failed || data?.status === 'unavailable' ? 'La consulta de focos recientes está temporalmente indisponible.'
      : data?.status === 'not_configured' ? 'La consulta automática requiere una clave de NASA FIRMS. El mapa histórico y el reporte guardado están disponibles en esta página.'
        : 'Consultando las detecciones recientes…'}</p>}
    <a className="button-link" href="https://firms.modaps.eosdis.nasa.gov/map/" target="_blank" rel="noreferrer">Abrir mapa NASA FIRMS <ArrowUpRight size={17} aria-hidden="true" /></a>
  </section>;
}
