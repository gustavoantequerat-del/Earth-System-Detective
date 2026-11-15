'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowUpRight } from 'lucide-react';
import { Area as ChartArea, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api, areaNames, imageUrl, modelUrl, number, signed, type Area, type BodyDetail, type Method, type WaterBody } from './data';
import { DataTable } from './ui';

const indicators = {
  forest_loss_ha: { label: 'Pérdida de bosque', description: 'Hectáreas de bosque perdido por año.', color: '#85e48e', unit: 'ha', source: 'Hansen Global Forest Change' },
  burned_ha: { label: 'Superficie quemada', description: 'Hectáreas de superficie quemada por año.', color: '#ffad85', unit: 'ha', source: 'NASA MODIS MCD64A1' },
  pasture_ha: { label: 'Pasturas', description: 'Hectáreas clasificadas como pastura en cada año.', color: '#b5db75', unit: 'ha', source: 'MapBiomas Cobertura' },
  agri_ha: { label: 'Cultivos', description: 'Hectáreas clasificadas como agricultura en cada año.', color: '#ffdb79', unit: 'ha', source: 'MapBiomas Cobertura' },
  dry_crop_ha: { label: 'Cultivos en época seca', description: 'Superficie de cultivo con vegetación activa en época seca. Puede indicar riego.', color: '#a4bbff', unit: 'ha', source: 'Landsat · proxy de riego' },
  mining_ha: { label: 'Superficie minera', description: 'Superficie clasificada como minería. Puedes comparar su crecimiento año a año.', color: '#ffd39f', unit: 'ha', source: 'MapBiomas Cobertura' },
  urban_ha: { label: 'Superficie urbana', description: 'Superficie clasificada como infraestructura urbana.', color: '#bfa7ff', unit: 'ha', source: 'MapBiomas Cobertura' },
  population: { label: 'Población estimada', description: 'Estimación de habitantes en el área consultada.', color: '#79cfff', unit: 'personas', source: 'WorldPop' },
  night_lights: { label: 'Luces nocturnas', description: 'Índice de iluminación que ayuda a seguir cambios urbanos o industriales. El archivo armoniza dos sensores.', color: '#a6c7ff', unit: 'índice', source: 'DMSP-OLS y NASA VIIRS' },
  crop_water_hm3: { label: 'Agua evapotranspirada por cultivos', description: 'Estimación de agua evapotranspirada de mayo a octubre en zonas clasificadas como cultivo. Puede ayudar a investigar el riego.', color: '#6ce6db', unit: 'hm³', source: 'NASA MODIS MOD16 y MapBiomas' },
} as const;
type Indicator = keyof typeof indicators;

const changes = [
  { key: 'forest_loss', label: 'Bosque perdido' }, { key: 'pasture', label: 'Pastura nueva' },
  { key: 'agri', label: 'Cultivos nuevos' }, { key: 'urban', label: 'Área urbana nueva' }, { key: 'mining', label: 'Minería nueva' },
];

export default function Vegetation({ bodies, id, method, select, details }: {
  bodies: WaterBody[]; id: string; method: Method; select: (id: string) => void; details: string;
}) {
  const [area, setArea] = useState<Area>('subcuenca_local');
  const [indicator, setIndicator] = useState<Indicator>('forest_loss_ha');
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{ key: string; data?: BodyDetail; error?: string }>();
  const key = `${method}/${id}/${attempt}`;
  const current = result?.key === key ? result : undefined;

  useEffect(() => {
    const request = new AbortController();
    api<BodyDetail>(modelUrl(`bodies/${encodeURIComponent(id)}`, method), { signal: request.signal })
      .then((data) => setResult({ key, data }))
      .catch((error: Error) => { if (!request.signal.aborted) setResult({ key, error: error.message }); });
    return () => request.abort();
  }, [id, key, method]);

  const { context, vegetation = [] } = current?.data ?? {};
  const availableAreas = new Set(vegetation.map((row) => row.area));
  const selectedArea = availableAreas.has(area) ? area : (availableAreas.values().next().value ?? area);
  const series = vegetation.filter((row) => row.area === selectedArea && row.suspect === indicator).sort((a, b) => a.year - b.year);
  const timeline = series.length ? Array.from({ length: series.at(-1)!.year - series[0].year + 1 }, (_, index) => {
    const year = series[0].year + index;
    return { year, value: series.find((row) => row.year === year)?.value ?? null };
  }) : [];
  const item = indicators[indicator];
  const last = series.at(-1);
  const previous = last ? series.find((row) => row.year === last.year - 1) : undefined;

  return <>
    <div className="panel mission-filter">
      <label><span id="vegetation-lake-label">Lago o laguna</span><select aria-labelledby="vegetation-lake-label"
        value={id} onChange={(event) => select(event.target.value)}>
        {bodies.map((body) => <option key={body.body_id} value={body.body_id}>{body.name}</option>)}
      </select></label>
      <Link className="button-link" href={details}>Ver ficha del lago <ArrowUpRight size={16} aria-hidden="true" /></Link>
    </div>
    {!current && <p className="loading" role="status">Cargando los datos de vegetación…</p>}
    {current?.error && <div className="notice danger" role="alert"><p>{current.error}</p>
      <button type="button" onClick={() => setAttempt((value) => value + 1)}>Reintentar</button></div>}
    {current?.data && <>
      <section className="panel mission-data-panel" aria-labelledby="vegetation-series">
        <div className="mission-chart-heading">
          <div><h2 id="vegetation-series" tabIndex={-1}>Cobertura y actividad humana</h2><p>{item.description}</p></div>
          <div className="mission-chart-controls">
            <label><span id="vegetation-area-label">Área</span><select aria-labelledby="vegetation-area-label"
              value={selectedArea} onChange={(event) => setArea(event.target.value as Area)}>
              {(Object.entries(areaNames) as [Area, string][]).map(([key, label]) => <option key={key} value={key}
                disabled={!availableAreas.has(key)}>{label}</option>)}
            </select></label>
            <label><span id="vegetation-indicator-label">Indicador</span><select aria-labelledby="vegetation-indicator-label"
              value={indicator} onChange={(event) => setIndicator(event.target.value as Indicator)}>
              {(Object.entries(indicators) as [Indicator, typeof item][]).map(([key, option]) => <option value={key} key={key}>{option.label}</option>)}
            </select></label>
          </div>
        </div>
        {timeline.length ? <>
          <div className="environment-metrics">
            {last && <div><span>Último dato · {last.year}</span><strong>{number(last.value, 1)} {item.unit}</strong><small>{item.source}</small></div>}
            {last && previous && <div><span>Cambio respecto a {previous.year}</span><strong>{signed(last.value - previous.value, 1)} {item.unit}</strong>
              <small>{areaNames[selectedArea]}</small></div>}
          </div>
          <div className="vegetation-chart" aria-label={`${item.label} de ${series[0].year} a ${series.at(-1)!.year}`}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={timeline} margin={{ top: 13, right: 18, left: 6, bottom: 14 }}>
                <CartesianGrid stroke="#294066" vertical={false} />
                <XAxis dataKey="year" stroke="#b9c7e3" minTickGap={30} />
                <YAxis stroke="#b9c7e3" width={75} tickFormatter={(value) => number(value)} unit={` ${item.unit}`} />
                <Tooltip contentStyle={{ background: '#101f3c', border: '1px solid #395581', borderRadius: 12 }}
                  formatter={(value) => [typeof value === 'number' ? `${number(value, 1)} ${item.unit}` : 'Sin dato', item.label]} />
                <ChartArea type="linear" dataKey="value" stroke={item.color} strokeWidth={3}
                  fill={item.color} fillOpacity={.15} isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <details className="mission-table-expand"><summary>Ver datos por año</summary>
            <DataTable rows={timeline.map(({ year, value }) => ({ Año: year, [`${item.label} (${item.unit})`]: value == null ? null : number(value, 1) }))} />
          </details>
        </> : <p className="notice">El archivo no tiene registros para este indicador y área.</p>}
      </section>
      <section className="mission-imagery" aria-labelledby="land-cover-images">
        <div className="mission-section-heading">
          <h2 id="land-cover-images" tabIndex={-1}>El paisaje desde satélite</h2>
          {context && <p>Comparación de {context.years[0]} a {context.years[1]} · Imagen Landsat de {number(context.window_km)} km de ancho.</p>}
        </div>
        {context ? <>
          <div className="mission-imagery-grid">
            {[
              { key: 'antes', label: `Antes · ${context.years[0]}` }, { key: 'despues', label: `Después · ${context.years[1]}` },
              { key: 'cambios', label: 'Cambios de cobertura' },
            ].map(({ key, label }) => <figure className="panel" key={key}>
              {/* This file is served by NestJS in local and deployed environments. */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={imageUrl('context', `${id}_${key}`)} alt={`${label} en ${current.data?.result.name}`} loading="lazy" />
              <figcaption>{label}</figcaption>
            </figure>)}
          </div>
          <ul className="mission-change-legend" aria-label="Cambios de cobertura en hectáreas">
            {changes.map(({ key, label }) => <li className="panel" key={key}>
              <span><i style={{ background: context.legend?.[key]?.color }} aria-hidden="true" />{label}</span>
              <strong>{context.changes_ha[key] == null ? '—' : `${number(context.changes_ha[key])} ha`}</strong>
            </li>)}
          </ul>
          <p className="muted">Los cambios corresponden a la ventana de las imágenes. La serie anual usa el área de cuenca seleccionada arriba.</p>
        </> : <p className="notice">Este caso no tiene una comparación satelital en el archivo.</p>}
      </section>
    </>}
  </>;
}
