'use client';

import { useEffect, useMemo, useState } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import { Area, CartesianGrid, ComposedChart, Legend, Line, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { AlertTriangle, ArrowDown, ArrowRight, ArrowUpRight, CheckCircle2, ClipboardList, Download, ExternalLink, Factory, Leaf, MountainSnow,
  ScanSearch, ShieldCheck, Sprout, Waves } from 'lucide-react';
import { api, downloadCsv, number, signed, states, type OsmKind, type RiverSummary } from './data';
import { DivergingBars, Donut } from './donut';
import { InfoTip, Status } from './ui';
import { kindColors, kindInfo, waterLegend, waterTone } from './rivers-palette';

const RiversMap = dynamic(() => import('./rivers-map'), {
  ssr: false, loading: () => <div className="rivers-map loading" role="status">Cargando mapa del río…</div>,
});

const axis = { fill: '#9fb8bd', fontSize: 12 };
const tooltipStyle = { background: '#0d2329', borderColor: '#2b4c54', color: '#e9f5f4', borderRadius: 10 };
const causeNames: Record<string, { label: string; color: string; info: string }> = {
  'Menos agua desde aguas arriba': { label: 'Menor aporte aguas arriba', color: '#56c4f5',
    info: 'Superficie que se explica porque el lago o el tramo de río que alimenta a la laguna aporta menos agua que en el periodo de referencia.' },
  'El Nino': { label: 'Episodios de El Niño', color: '#f7b84b', info: 'Efecto de los años con El Niño, que en el Altiplano suelen ser más secos.' },
  'Lluvia menos evaporacion': { label: 'Lluvia menos evaporación', color: '#fb923c', info: 'Efecto del balance local entre lluvia y evaporación.' },
  'Huella humana': { label: 'Presión humana local', color: '#f47067', info: 'Pérdida asociada a actividades humanas en la propia cuenca de la laguna.' },
  Incalculable: { label: 'No explicado', color: '#9aa9c7', info: 'Fracción que ningún factor medido explica: puede deberse a procesos en el recorrido del río o en la propia laguna.' },
};
const verdictLabel: Record<string, string> = {
  'Posible desvío': 'Indicio de desvío',
  'Pierde agua, sin señal de riego': 'Pérdida sin indicio de riego',
  'Sin pérdida significativa': 'Sin pérdida significativa',
};
const verdictTone: Record<string, { className: string; Icon: typeof CheckCircle2 }> = {
  'Posible desvío': { className: 'danger', Icon: AlertTriangle },
  'Pierde agua, sin señal de riego': { className: 'warning', Icon: AlertTriangle },
  'Sin pérdida significativa': { className: 'ok', Icon: CheckCircle2 },
};

export default function Rivers({ lake: requested, selectLake }: { lake?: string | null; selectLake: (id: string) => void }) {
  const [data, setData] = useState<RiverSummary>();
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [reach, setReach] = useState<string | null>(null);
  const [kinds, setKinds] = useState<Set<OsmKind>>(new Set(['Canal o acequia', 'Represa o toma', 'Mina o cantera', 'Reservorio', 'Planta de tratamiento']));

  useEffect(() => {
    const request = new AbortController();
    api<RiverSummary>('rivers', { signal: request.signal }).then(setData)
      .catch((reason: Error) => { if (!request.signal.aborted) setError(reason.message); });
    return () => request.abort();
  }, [attempt]);

  const lake = data?.lakes.find((item) => item.id === requested) ?? data?.lakes.find((item) => item.id === 'poopo') ?? data?.lakes[0];
  const byId = useMemo(() => new Map(data?.reaches.map((item) => [item.id, item]) ?? []), [data]);

  if (error) return <div className="notice danger" role="alert"><p>{error}</p>
    <button type="button" onClick={() => { setError(''); setAttempt((value) => value + 1); }}>Reintentar</button></div>;
  if (!data || !lake) return <p className="loading" role="status">Cargando el análisis del río…</p>;

  const lakeReaches = lake.reaches;
  const flow = ['T1', 'T2', 'M', 'T3', 'T4', 'T5', ...(lakeReaches.includes('T6') ? ['T6'] : [])].filter((id) => byId.has(id));
  const current = byId.get(reach && lakeReaches.includes(reach) ? reach : 'T1')!;
  const t1 = byId.get('T1')!;
  const greenDelta = (lake.green_recent_ha ?? 0) - (lake.green_base_ha ?? 0);
  const works = Object.values(lake.osm).reduce((sum, value) => sum + value, 0);
  const useMax = Math.max(...lakeReaches.map((id) => byId.get(id)?.consumptive_use_pct ?? 0));
  const [b0, b1] = data.period.base;
  const [r0, r1] = data.period.recent;

  const losses = Object.entries(lake.decomposition_ha).filter(([, value]) => (value ?? 0) < 0)
    .map(([key, value]) => ({ key, label: causeNames[key]?.label ?? key, value: -(value ?? 0), color: causeNames[key]?.color ?? '#9aa9c7', note: causeNames[key]?.info }))
    .sort((a, b) => b.value - a.value);
  const gains = Object.entries(lake.decomposition_ha).filter(([, value]) => (value ?? 0) > 0);
  const lossTotal = losses.reduce((sum, item) => sum + item.value, 0);
  const upstream = losses.find((item) => item.key === 'Menos agua desde aguas arriba');
  const net = lossTotal - gains.reduce((sum, [, value]) => sum + (value ?? 0), 0);
  // mismo criterio que el motor: lo que deja de llegar frente a la pérdida neta de la laguna
  const upstreamShare = upstream && net > 0 ? upstream.value / net * 100 : null;
  const split = lake.upstream_split;

  const series = data.years.map((year, index) => ({
    year, water: data.series[current.id].water[index], green: data.series[current.id].green[index],
    greenFilled: data.series[current.id].green[index] == null ? data.series[current.id].green_filled[index] : null,
  }));
  const pairs = data.diversion.filter((pair) => lakeReaches.includes(pair.to));
  const flagged = pairs.filter((pair) => pair.verdict !== 'Sin pérdida significativa');
  const topGreen = lakeReaches.map((id) => byId.get(id)).filter((item) => item != null)
    .sort((a, b) => (b!.green.delta ?? 0) - (a!.green.delta ?? 0))[0];

  function exportCsv() {
    downloadCsv(data!.reaches.filter((item) => lakeReaches.includes(item.id)).map((item) => ({
      Tramo: item.id, Nombre: item.name, 'Km desde el Titicaca': item.km ? `${item.km[0]}-${item.km[1]}` : 'afluente',
      [`Agua en el cauce ${b0}-${b1} (ha)`]: item.water.base, [`Agua en el cauce ${r0}-${r1} (ha)`]: item.water.recent,
      'Cambio agua (%)': item.water.pct, [`Verde en seca ${b0}-${b1} (ha)`]: item.green.base, [`Verde en seca ${r0}-${r1} (ha)`]: item.green.recent,
      'Cambio verde (ha)': item.green.delta, 'Uso consuntivo HydroSHEDS (%)': item.consumptive_use_pct,
      ...Object.fromEntries(Object.entries(item.osm).map(([kind, count]) => [`OSM ${kind}`, count])),
    })), `rio_desaguadero_${lake!.id}.csv`);
  }

  return <div className="rivers">
    <section className="rivers-intro panel" aria-labelledby="rivers-question">
      <div>
        <p className="mission-eyebrow">Sistema Titicaca – Desaguadero – Poopó</p>
        <h2 id="rivers-question">¿Dónde se origina la pérdida de agua?</h2>
        <p>Uru Uru y Poopó dependen menos de la lluvia local que del aporte del río Desaguadero, que nace en el Titicaca y recibe al
          Mauri. Este módulo sigue el río tramo a tramo con imágenes satelitales para localizar dónde disminuye el agua y qué
          presiones humanas hay a su alrededor.</p>
      </div>
      <fieldset className="rivers-lake-switch">
        <legend>Cuerpo de agua receptor</legend>
        <div>{data.lakes.map((item) => <label key={item.id}>
          <input type="radio" name="river-lake" checked={item.id === lake.id} onChange={() => { setReach(null); selectLake(item.id); }} />
          <span>{item.name}</span>
        </label>)}</div>
      </fieldset>
    </section>

    <section className="panel rivers-verdict" aria-labelledby="rivers-verdict-title">
      <div className="rivers-verdict-copy">
        <div className="rivers-verdict-head">
          {lake.state && <Status state={lake.state} />}
          <span className="rivers-confidence">Confianza {lake.confidence?.toLowerCase()}
            <InfoTip label="Confianza y robustez" align="start">
              Indica cuánto respaldan el diagnóstico las tres pruebas del detector: ajuste climático, comparación con una laguna de control y coincidencia temporal del cambio.
              {lake.robustness && ` El diagnóstico se mantiene en ${lake.robustness.agree} de ${lake.robustness.of} variantes del modelo (memoria de lluvia de 1 a 8 años).`}
            </InfoTip>
          </span>
        </div>
        <h3 id="rivers-verdict-title">{lake.state === 'Aguas arriba'
          ? <>La pérdida del {lake.name.replace(/^Lago /, 'lago ')} se origina <mark>aguas arriba</mark>: llega menos agua por el Desaguadero</>
          : <>{lake.name}: {lake.state ? states[lake.state].label.toLowerCase() : 'sin veredicto'}</>}</h3>
        {upstreamShare != null && <p className="rivers-big-number"><strong>{upstreamShare >= 100 ? '100 %' : `${number(upstreamShare)} %`}</strong>
          <span>{upstreamShare >= 100
            ? `de la pérdida neta de superficie (${number(net)} ha) corresponde al menor aporte desde ${lake.upstream_source?.name ?? 'aguas arriba'}; el déficit de aporte (${number(upstream!.value)} ha) incluso la supera.`
            : `de la pérdida neta de superficie (${number(net)} ha) corresponde al menor aporte desde ${lake.upstream_source?.name ?? 'aguas arriba'}.`}</span></p>}
        <ul className="rivers-facts">
          <li><Waves size={18} aria-hidden="true" /> Superficie de agua: {lake.change_pct == null ? 's/d' : `${lake.change_pct < 0 ? '−' : '+'}${number(Math.abs(lake.change_pct))} %`} respecto del periodo de referencia {b0}–{b1}.</li>
          <li><ScanSearch size={18} aria-hidden="true" /> {split?.human_max_ha == null
            ? `La fracción atribuible a la acción humana aún no puede acotarse: el diagnóstico de ${lake.upstream_source?.name ?? 'la fuente'} es «${lake.upstream_source ? states[lake.upstream_source.state]?.label.toLowerCase() : 'incierto'}».`
            : `La fracción atribuible a la acción humana es, como máximo, ${number(split.human_max_ha)} ha.`}</li>
          <li><MountainSnow size={18} aria-hidden="true" /> Acotarla requiere series de nivel del Titicaca y de caudal del Desaguadero medidas en estaciones (SENAMHI, ALT).</li>
        </ul>
      </div>
      <figure className="rivers-verdict-chart">
        <figcaption className="with-info">Factores de la pérdida
          <InfoTip label="Factores de la pérdida" align="end">El modelo descompone la diferencia de superficie entre {b0}–{b1} y los últimos cinco años según su origen. Pasa el cursor por cada color para ver su peso relativo.
            {gains.length > 0 && ` Atenuaron la pérdida: ${gains.map(([key, value]) => `${causeNames[key]?.label ?? key} (+${number(value ?? 0)} ha)`).join(', ')}.`}</InfoTip>
        </figcaption>
        <Donut label="Factores de la pérdida" slices={losses} unit="ha" centerLabel="ha de déficit" size={200} />
      </figure>
    </section>

    <div className="rivers-kpis">
      <article className="panel rivers-kpi">
        <div className="rivers-kpi-top"><Waves size={20} aria-hidden="true" /><InfoTip label="Superficie de agua en el cauce" align="start">
          Superficie de agua visible en el primer tramo del Desaguadero (franja de 1 km, MapBiomas Agua): promedio {b0}–{b1} de {number(t1.water.base ?? 0)} ha frente a {number(t1.water.recent ?? 0)} ha en {r0}–{r1}. Es un indicador del ancho de la lámina de agua, no una medición de caudal.</InfoTip></div>
        <strong style={{ color: waterTone(t1.water.pct).css }}>{signed(t1.water.pct ?? 0)} %</strong>
        <span>superficie de agua en el cauce a la salida del Titicaca</span>
        <Gauge base={t1.water.base} recent={t1.water.recent} color={waterTone(t1.water.pct).css} />
      </article>
      <article className="panel rivers-kpi">
        <div className="rivers-kpi-top"><Sprout size={20} aria-hidden="true" /><InfoTip label="Vegetación activa en estiaje">
          Entre junio y octubre casi no llueve en el Altiplano: la vegetación que sigue verde es riego o bofedal. Se cuentan las hectáreas con NDVI mayor a 0,3 (Landsat) en una franja de 5 km a cada lado del río. Su aumento es un indicador indirecto de extracción para riego.</InfoTip></div>
        <strong className="pos-amber">{signed(greenDelta)} ha</strong>
        <span>de vegetación activa en estiaje junto al río (indicador de riego)</span>
        <small>{number(lake.green_base_ha ?? 0)} → {number(lake.green_recent_ha ?? 0)} ha</small>
      </article>
      <article className="panel rivers-kpi">
        <div className="rivers-kpi-top"><Factory size={20} aria-hidden="true" /><InfoTip label="Infraestructura y actividades registradas">
          Canales, tomas, represas, reservorios, minas y plantas de tratamiento registrados en OpenStreetMap a menos de 15 km del río o 45 km de la laguna. Es un inventario colaborativo y puede estar incompleto: no sustituye un catastro oficial de derechos de uso.</InfoTip></div>
        <strong>{number(works)}</strong>
        <span>elementos de infraestructura hídrica y actividad extractiva</span>
        <small>{number(lake.osm['Canal o acequia'])} canales · {number(lake.osm['Mina o cantera'])} minas</small>
      </article>
      <article className="panel rivers-kpi">
        <div className="rivers-kpi-top"><Leaf size={20} aria-hidden="true" /><InfoTip label="Uso consuntivo" align="end">
          Estimación global de HydroSHEDS (Grill et al. 2019): porcentaje del caudal natural que se consume en riego, uso urbano e industria. Un valor bajo sugiere que la extracción documentada es pequeña frente al volumen del río.</InfoTip></div>
        <strong>{number(useMax, 1)} %</strong>
        <span>del caudal natural es uso consuntivo (HydroSHEDS)</span>
        <small>Valor más alto entre los tramos</small>
      </article>
    </div>

    <section className="panel rivers-actions" aria-labelledby="rivers-actions-title">
      <h2 id="rivers-actions-title" className="with-info"><ClipboardList size={22} aria-hidden="true" /> Implicancias para la gestión
        <InfoTip label="Implicancias para la gestión" align="start">Recomendaciones derivadas automáticamente de los resultados de esta página. Son orientativas: priorizan dónde medir e inspeccionar, no reemplazan la verificación en campo.</InfoTip></h2>
      <ol>
        {lake.state === 'Aguas arriba' && <li><b>Gestionar a escala de cuenca.</b> La causa principal está aguas arriba: las medidas aplicadas solo en el {lake.name.replace(/^Lago /, 'lago ')} tendrán un efecto limitado sin coordinación en el sistema TDPS (Titicaca–Desaguadero–Poopó–Salar de Coipasa).</li>}
        {split?.human_max_ha == null && <li><b>Cerrar la brecha de información.</b> Priorizar series continuas de nivel del Titicaca y de caudal del Desaguadero para estimar qué parte de la pérdida es atribuible a la acción humana.</li>}
        {topGreen && (topGreen.green.delta ?? 0) > 50 && <li><b>Verificar el uso de agua para riego.</b> {topGreen.id === 'M' ? 'El río Mauri' : `El tramo ${topGreen.id} (${topGreen.name})`} concentra el mayor aumento de vegetación en estiaje ({signed(topGreen.green.delta ?? 0)} ha): conviene contrastarlo con los derechos de uso otorgados.</li>}
        {lake.osm['Mina o cantera'] > 0 && <li><b>Vigilar la calidad del agua.</b> Hay {number(lake.osm['Mina o cantera'])} minas o canteras registradas en el área de influencia; su efecto sobre el volumen no es medible desde el satélite, pero sí relevante para la calidad.</li>}
        {flagged.length === 0 && <li><b>Sin indicios de desvío entre tramos.</b> No se detectan pérdidas significativas entre tramos consecutivos con los datos actuales.</li>}
      </ol>
    </section>

    <section className="panel rivers-flow" aria-labelledby="rivers-flow-title">
      <div className="mission-chart-heading">
        <div><h2 id="rivers-flow-title" className="with-info">Recorrido del agua, tramo a tramo
          <InfoTip label="Recorrido del agua" align="start">Cada tarjeta es un tramo del río. El relleno muestra la superficie de agua actual en el cauce como proporción de la de {b0}–{b1}. Selecciona un tramo para ver su serie anual.</InfoTip></h2>
          <p>Desde la salida del Titicaca hasta la laguna receptora. Selecciona un tramo para ver el detalle.</p></div>
        <ul className="rivers-legend" aria-label="Colores de los tramos">{waterLegend.map((item) => <li key={item.label}><i style={{ background: item.css }} />{item.label}</li>)}</ul>
      </div>
      <ol className="rivers-chain">
        <li className="rivers-node source"><MountainSnow size={20} aria-hidden="true" /><b>Lago Titicaca</b><small>origen</small></li>
        {flow.map((id) => {
          const item = byId.get(id)!;
          const ratio = item.water.base ? Math.min(1.2, (item.water.recent ?? 0) / item.water.base) : null;
          const color = waterTone(item.water.pct).css;
          return <li key={id} className={id === 'M' ? 'rivers-node tributary' : 'rivers-node'}>
            <button type="button" aria-pressed={current.id === id} onClick={() => setReach(id)}
              aria-label={`${id} ${item.name}: ${item.water.pct == null ? 'sin dato' : signed(item.water.pct) + ' % de superficie de agua en el cauce'}`}>
              <span className="rivers-level" aria-hidden="true"><i style={{ height: `${(ratio ?? 0) / 1.2 * 100}%`, background: color }} /></span>
              <b>{id === 'M' ? 'Mauri' : id}</b>
              <small>{id === 'M' ? 'afluente (nace en Perú)' : item.name}</small>
              <em style={{ color }}>{item.water.pct == null ? 's/d' : `${signed(item.water.pct)} %`}</em>
            </button>
          </li>;
        })}
        <li className="rivers-node sink"><Waves size={20} aria-hidden="true" /><b>{lake.name.replace(/^Lago /, '')}</b>
          <small>{lake.change_pct == null ? '' : `${signed(lake.change_pct)} % de superficie`}</small></li>
      </ol>
    </section>

    <div className="rivers-grid">
      <section className="panel rivers-map-panel" aria-labelledby="rivers-map-title">
        <div className="mission-chart-heading"><div>
          <h2 id="rivers-map-title" className="with-info">Mapa de tramos y presiones
            <InfoTip label="Mapa de tramos y presiones" align="start">El color de cada tramo indica el cambio de superficie de agua en su cauce. Los puntos son infraestructura y actividades registradas en OpenStreetMap. Haz clic en un tramo para seleccionarlo.</InfoTip></h2>
          <p>Imagen satelital con el cauce y las presiones registradas en su entorno.</p></div></div>
        <div className="rivers-kind-filter" role="group" aria-label="Capas visibles en el mapa">
          {(Object.keys(kindColors) as OsmKind[]).filter((kind) => data.osm_totals[kind]).map((kind) =>
            <button type="button" key={kind} aria-pressed={kinds.has(kind)} onClick={() => setKinds((previous) => {
              const next = new Set(previous);
              if (next.has(kind)) next.delete(kind); else next.add(kind);
              return next;
            })}><i style={{ background: kindColors[kind].css }} aria-hidden="true" />{kind}</button>)}
        </div>
        <RiversMap data={data} lakeReaches={lakeReaches} selected={current.id} onSelect={setReach} kinds={kinds} />
      </section>
      <section className="panel rivers-works" aria-labelledby="rivers-works-title">
        <h2 id="rivers-works-title" className="with-info">Presiones registradas
          <InfoTip label="Tipos de presión" align="end">{(Object.keys(kindInfo) as OsmKind[]).map((kind) => <span key={kind} className="tip-row"><b>{kind}:</b> {kindInfo[kind]}</span>)}</InfoTip></h2>
        <Donut label="Presiones registradas" centerLabel="elementos registrados" size={190}
          slices={(Object.keys(kindColors) as OsmKind[]).map((kind) => ({ key: kind, label: kind, value: lake.osm[kind], color: kindColors[kind].css }))} />
        <p className="muted">Fuente: OpenStreetMap. En el entorno de Uru Uru, buena parte de los «canales» corresponde al drenaje urbano de Oruro.</p>
      </section>
    </div>

    <section className="panel rivers-reach" aria-labelledby="rivers-reach-title">
      <div className="mission-chart-heading">
        <div><p className="mission-eyebrow">Tramo seleccionado</p>
          <h2 id="rivers-reach-title">{current.id === 'M' ? 'Río Mauri' : `${current.id} · ${current.name}`}</h2>
          <p>{current.km ? `Del kilómetro ${current.km[0]} al ${current.km[1]}, contados desde la salida del Titicaca.` : 'Afluente transfronterizo: nace en Perú y confluye con el Desaguadero en Calacoto.'}</p></div>
        <label><span>Tramo</span><select value={current.id} onChange={(event) => setReach(event.target.value)}>
          {flow.map((id) => <option key={id} value={id}>{id === 'M' ? 'Mauri' : `${id} · ${byId.get(id)!.name}`}</option>)}
        </select></label>
      </div>
      <div className="rivers-reach-body">
        <div className="rivers-chips">
          <Chip label="Superficie de agua en el cauce" value={current.water.pct == null ? 's/d' : `${signed(current.water.pct)} %`} color={waterTone(current.water.pct).css}
            info={`Promedio ${b0}–${b1}: ${number(current.water.base ?? 0)} ha. Promedio ${r0}–${r1}: ${number(current.water.recent ?? 0)} ha.`} />
          <Chip label="Vegetación activa en estiaje" value={`${signed(current.green.delta ?? 0)} ha`} color="#f7b84b"
            info={`De ${number(current.green.base ?? 0)} a ${number(current.green.recent ?? 0)} ha con vegetación activa entre junio y octubre, en 5 km a cada lado del río. Incluye bofedales naturales; lo relevante es la variación.`} />
          <Chip label="Superficie agrícola" value={current.crops.pct == null ? 's/d' : `${signed(current.crops.pct)} %`} color="#a3e635"
            info={`Superficie agrícola en 5 km a cada lado del río según MapBiomas Bolivia: ${number(current.crops.base ?? 0)} → ${number(current.crops.recent ?? 0)} ha.`} />
          <Chip label="Cuerpos de agua artificiales" value={`${signed(current.artificial.delta ?? 0)} ha`} color="#818cf8"
            info="Variación de la superficie de represas, reservorios y estanques en 5 km a cada lado del río, según MapBiomas Agua." />
        </div>
        <figure className="rivers-chart">
          <div className="chart"><ResponsiveContainer width="100%" height="100%" minWidth={0}>
            <ComposedChart data={series} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="#1d3a41" vertical={false} />
              <ReferenceArea x1={b0} x2={b1} fill="#56c4f5" fillOpacity={0.07} label={{ value: 'Referencia', fill: '#9fb8bd', fontSize: 11, position: 'insideTop' }} />
              <XAxis dataKey="year" tick={axis} type="number" domain={['dataMin', 'dataMax']} tickCount={8} />
              <YAxis tick={axis} width={52} tickFormatter={(value) => number(Number(value))} />
              <Tooltip contentStyle={tooltipStyle} formatter={(value, name) => [`${number(Number(value))} ha`, name]} labelFormatter={(value) => `Año ${value}`} />
              <Legend />
              <Area dataKey="water" name="Superficie de agua en el cauce" type="monotone" stroke="#56c4f5" fill="#56c4f5" fillOpacity={0.22} strokeWidth={2} />
              <Line dataKey="green" name="Vegetación activa en estiaje" type="monotone" stroke="#f7b84b" strokeWidth={2} dot={false} connectNulls={false} />
              <Line dataKey="greenFilled" name="Año sin imagen (interpolado)" type="monotone" stroke="#f7b84b" strokeDasharray="2 3" dot={{ r: 3 }} legendType="none" />
            </ComposedChart>
          </ResponsiveContainer></div>
          <figcaption>Hectáreas por año. La franja sombreada es el periodo de referencia {b0}–{b1}. Para 2002 no hay mosaico Landsat de estiaje: el valor se interpola y se marca con puntos.</figcaption>
        </figure>
      </div>
    </section>

    <div className="rivers-diversion-wrap">
      <div className="mission-section-heading">
        <h2 className="with-info">Prueba de desvío entre tramos
          <InfoTip label="Prueba de desvío" align="start">Con el periodo {b0}–{b1} se calibra la relación entre cada tramo y el anterior. Luego se evalúa si el tramo inferior recibe cada vez menos agua de la esperada (Mann–Kendall con corrección por autocorrelación; p menor a 0,05 y al menos −10 %). Si además aumenta la vegetación en estiaje o hay canales registrados, se señala un indicio de desvío.</InfoTip></h2>
        <p>¿Recibe cada tramo el agua que le corresponde según el tramo anterior?</p>
      </div>
      <div className="rivers-diversion">
        {pairs.map((pair) => {
          const verdict = verdictTone[pair.verdict] ?? verdictTone['Sin pérdida significativa'];
          const mini = data.years.map((year, index) => ({ year, expected: pair.expected[index], observed: pair.observed[index] }));
          return <article key={pair.to} className={`panel rivers-pair ${verdict.className}`}>
            <header><b>{pair.from} <ArrowRight size={14} aria-hidden="true" /> {pair.to}</b><span className={`pair-badge ${verdict.className}`}><verdict.Icon size={14} aria-hidden="true" />{verdictLabel[pair.verdict] ?? pair.verdict}</span></header>
            <p>{pair.to_name}</p>
            <div className="pair-chart" aria-hidden="true"><ResponsiveContainer width="100%" height="100%" minWidth={0}>
              <ComposedChart data={mini} margin={{ top: 4, right: 4, left: 4, bottom: 0 }}>
                <XAxis dataKey="year" hide /><YAxis hide />
                <Line dataKey="expected" stroke="#9fb8bd" strokeDasharray="4 3" dot={false} strokeWidth={1.5} />
                <Line dataKey="observed" stroke="#56c4f5" dot={false} strokeWidth={2} />
              </ComposedChart>
            </ResponsiveContainer></div>
            <dl>
              <div><dt>Diferencia con lo esperado</dt><dd>{pair.missing_pct == null ? 's/d' : `${signed(pair.missing_pct)} %`}</dd></div>
              <div><dt>Vegetación en estiaje</dt><dd>{signed(pair.green_delta_ha ?? 0)} ha</dd></div>
              <div><dt>Canales y tomas</dt><dd>{number(pair.canals)}</dd></div>
            </dl>
            <small>p = {pair.p == null ? 's/d' : number(pair.p, 3)} · línea punteada: esperado · línea azul: observado</small>
          </article>;
        })}
      </div>
      <p className="muted">{flagged.length
        ? `Conclusión: ${flagged.map((pair) => `${pair.from}→${pair.to} (${(verdictLabel[pair.verdict] ?? pair.verdict).toLowerCase()})`).join(', ')}.`
        : 'Conclusión: ningún tramo muestra una pérdida significativa respecto del anterior.'}
        {(t1.water.pct ?? 0) <= -40 && ' La disminución ya es visible a la salida del Titicaca, lo que apunta al nivel del lago antes que a extracciones en el recorrido.'}
        {' '}Limitación: se mide la superficie de agua, no el caudal, por lo que una extracción pequeña podría pasar inadvertida. La misión SWOT (NASA/CNES, desde 2023) permitirá estimar caudales.</p>
    </div>

    <section className="panel rivers-changes" aria-labelledby="rivers-changes-title">
      <h2 id="rivers-changes-title" className="with-info">Variación de la superficie de agua por tramo
        <InfoTip label="Variación por tramo" align="start">Cambio porcentual de la superficie de agua en el cauce: promedio {r0}–{r1} frente a {b0}–{b1}. Hacia la izquierda, disminución; hacia la derecha, aumento.</InfoTip></h2>
      <DivergingBars max={100} rows={flow.map((id) => {
        const item = byId.get(id)!;
        return { key: id, label: id === 'M' ? 'Mauri' : id, hint: id === 'M' ? 'afluente' : item.name, value: item.water.pct, color: waterTone(item.water.pct).css };
      })} />
    </section>

    <section className="panel rivers-quality" aria-labelledby="rivers-quality-title">
      <div className="mission-chart-heading">
        <div><h2 id="rivers-quality-title"><ShieldCheck size={22} aria-hidden="true" /> Calidad y trazabilidad de los datos</h2>
          <p>Controles automáticos aplicados a los datos de este módulo. Los avisos se muestran sin filtrar.</p></div>
        <div className="rivers-downloads">
          <button type="button" onClick={exportCsv}><Download size={16} aria-hidden="true" /> Tabla por tramo (CSV)</button>
          <a className="button-link" href="/api/rivers" download="rio_resumen.json"><Download size={16} aria-hidden="true" /> Análisis completo (JSON)</a>
        </div>
      </div>
      <ul className="rivers-checks">{data.quality.map((check) => <li key={check.label} className={!check.ok ? 'fail' : check.warn ? 'warn' : 'ok'}>
        {!check.ok || check.warn ? <AlertTriangle size={18} aria-hidden="true" /> : <CheckCircle2 size={18} aria-hidden="true" />}
        <div><b>{check.label}</b><p>{check.detail}</p></div>
      </li>)}</ul>
      <h3>Fuentes de datos</h3>
      <ul className="rivers-sources">{data.sources.map((source) => <li key={source.name}>
        <a href={source.url} target="_blank" rel="noreferrer">{source.name} <ExternalLink size={13} aria-hidden="true" /></a><span>{source.use}</span>
      </li>)}</ul>
      <details className="rivers-why"><summary>Razonamiento del modelo</summary>
        <ul>{lake.why.map((reason) => <li key={reason}>{reason}</li>)}</ul></details>
      <p className="muted">Análisis generado el {data.generated}. <Link href={`/?vista=ficha&laguna=${lake.id}`}>Ver la ficha completa de la laguna <ArrowUpRight size={13} aria-hidden="true" /></Link>
        {' '}· <a href="#contenido">Volver arriba <ArrowDown size={13} style={{ rotate: '180deg' }} aria-hidden="true" /></a></p>
    </section>
  </div>;
}

function Gauge({ base, recent, color }: { base: number | null; recent: number | null; color: string }) {
  if (!base || recent == null) return null;
  return <div className="rivers-gauge" aria-hidden="true">
    <span><i style={{ width: '100%' }} /><small>antes</small></span>
    <span><i style={{ width: `${Math.min(100, recent / base * 100)}%`, background: color }} /><small>hoy</small></span>
  </div>;
}

function Chip({ label, value, color, info }: { label: string; value: string; color: string; info: string }) {
  return <div className="rivers-chip"><span>{label} <InfoTip label={label} align="start">{info}</InfoTip></span><strong style={{ color }}>{value}</strong></div>;
}
