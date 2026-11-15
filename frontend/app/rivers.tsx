'use client';

import { useEffect, useMemo, useState } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import { Area, CartesianGrid, ComposedChart, Legend, Line, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { AlertTriangle, ArrowDown, ArrowRight, ArrowUpRight, CheckCircle2, Download, ExternalLink, Factory, Leaf, MountainSnow,
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
  'Menos agua desde aguas arriba': { label: 'Llega menos agua por el río', color: '#56c4f5',
    info: 'Hectáreas de laguna que se explican porque el lago o el tramo del río que la alimenta trae menos agua que antes.' },
  'El Nino': { label: 'Años de El Niño', color: '#f7b84b', info: 'Efecto de los años de El Niño, que en el Altiplano suelen ser más secos.' },
  'Lluvia menos evaporacion': { label: 'Lluvia menos evaporación', color: '#fb923c', info: 'Efecto del balance local entre lluvia y evaporación.' },
  'Huella humana': { label: 'Huella humana directa', color: '#f47067', info: 'Pérdida asociada a actividades humanas en la propia cuenca de la laguna.' },
  Incalculable: { label: 'Sin explicar', color: '#9aa9c7', info: 'Parte de la pérdida que ningún factor medido explica. Puede deberse a lo que pasa en el camino o en la laguna.' },
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
        <p className="mission-eyebrow">Río Desaguadero · del Titicaca al Poopó</p>
        <h2 id="rivers-question">¿Por qué le falta agua a la laguna?</h2>
        <p>Las lagunas Uru Uru y Poopó no viven de su lluvia: se llenan con el agua que baja del Titicaca por el río Desaguadero
          y el Mauri. Aquí seguimos el río tramo a tramo con satélites para ver dónde se pierde el agua y qué hay en el camino.</p>
      </div>
      <fieldset className="rivers-lake-switch">
        <legend>Laguna que quieres analizar</legend>
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
              Resume si las 3 pruebas del detector (clima, laguna de control y momento del cambio) respaldan una causa en la propia laguna.
              {lake.robustness && ` El veredicto se repite en ${lake.robustness.agree} de ${lake.robustness.of} variantes del modelo (de 1 a 8 años de memoria de lluvia).`}
            </InfoTip>
          </span>
        </div>
        <h3 id="rivers-verdict-title">{lake.state === 'Aguas arriba'
          ? <>El {lake.name.replace(/^Lago /, 'lago ')} pierde agua porque <mark>llega menos por el río</mark></>
          : <>{lake.name}: {lake.state ? states[lake.state].label.toLowerCase() : 'sin veredicto'}</>}</h3>
        {upstreamShare != null && <p className="rivers-big-number"><strong>{upstreamShare >= 100 ? '100 %' : `${number(upstreamShare)} %`}</strong>
          <span>{upstreamShare >= 100
            ? `de la pérdida neta (${number(net)} ha) se explica por lo que deja de llegar desde ${lake.upstream_source?.name ?? 'aguas arriba'}: llegan ${number(upstream!.value)} ha menos.`
            : `de la pérdida neta (${number(net)} ha) se explica por lo que deja de llegar desde ${lake.upstream_source?.name ?? 'aguas arriba'}.`}</span></p>}
        <ul className="rivers-facts">
          <li><Waves size={18} aria-hidden="true" /> La laguna tiene {lake.change_pct == null ? 's/d' : `${number(Math.abs(lake.change_pct))} % ${lake.change_pct < 0 ? 'menos' : 'más'}`} superficie de agua que en {b0}–{b1}.</li>
          <li><ScanSearch size={18} aria-hidden="true" /> {split?.human_max_ha == null
            ? `Cuánto de eso es humano todavía no se puede acotar: ${lake.upstream_source?.name ?? 'la fuente'} tiene veredicto ${lake.upstream_source ? states[lake.upstream_source.state]?.label.toLowerCase() : 'incierto'}.`
            : `La parte humana de lo que deja de llegar es como mucho ${number(split.human_max_ha)} ha.`}</li>
          <li><MountainSnow size={18} aria-hidden="true" /> Para cerrar la duda hacen falta el nivel medido del Titicaca y el caudal del Desaguadero en estaciones (SENAMHI, ALT).</li>
        </ul>
      </div>
      <figure className="rivers-verdict-chart">
        <figcaption className="with-info">¿Qué explica la pérdida?
          <InfoTip label="Qué explica la pérdida" align="end">El modelo separa las hectáreas perdidas entre el periodo {b0}–{b1} y los últimos cinco años en sus partes. Pasa el mouse sobre cada color para ver su peso.
            {gains.length > 0 && ` Compensaron en parte: ${gains.map(([key, value]) => `${causeNames[key]?.label ?? key} (+${number(value ?? 0)} ha)`).join(', ')}.`}</InfoTip>
        </figcaption>
        <Donut label="Partes de la pérdida" slices={losses} unit="ha" centerLabel="ha perdidas" size={200} />
      </figure>
    </section>

    <div className="rivers-kpis">
      <article className="panel rivers-kpi">
        <div className="rivers-kpi-top"><Waves size={20} aria-hidden="true" /><InfoTip label="Agua a la salida del Titicaca" align="start">
          Superficie de agua visible en el cauce del primer tramo del Desaguadero (franja de 1 km, MapBiomas Agua). Compara el promedio {b0}–{b1} ({number(t1.water.base ?? 0)} ha) con {r0}–{r1} ({number(t1.water.recent ?? 0)} ha). Mide el ancho del agua, no el caudal.</InfoTip></div>
        <strong style={{ color: waterTone(t1.water.pct).css }}>{signed(t1.water.pct ?? 0)} %</strong>
        <span>agua en el río a la salida del Titicaca</span>
        <Gauge base={t1.water.base} recent={t1.water.recent} color={waterTone(t1.water.pct).css} />
      </article>
      <article className="panel rivers-kpi">
        <div className="rivers-kpi-top"><Sprout size={20} aria-hidden="true" /><InfoTip label="Verde en época seca">
          En el Altiplano casi nada está verde de junio a octubre, salvo lo que se riega y los bofedales. Contamos las hectáreas verdes (Landsat, NDVI mayor a 0,3) a 5 km del río. Si crecen, crece el riego con agua del río.</InfoTip></div>
        <strong className="pos-amber">{signed(greenDelta)} ha</strong>
        <span>de verde en época seca junto al río (posible riego)</span>
        <small>{number(lake.green_base_ha ?? 0)} → {number(lake.green_recent_ha ?? 0)} ha</small>
      </article>
      <article className="panel rivers-kpi">
        <div className="rivers-kpi-top"><Factory size={20} aria-hidden="true" /><InfoTip label="Obras y actividades registradas">
          Canales, tomas, represas, reservorios, minas y plantas de tratamiento registrados en OpenStreetMap a menos de 15 km del río o 45 km de la laguna. Es un inventario colaborativo: puede estar incompleto.</InfoTip></div>
        <strong>{number(works)}</strong>
        <span>obras y actividades en el camino del agua</span>
        <small>{number(lake.osm['Canal o acequia'])} canales · {number(lake.osm['Mina o cantera'])} minas</small>
      </article>
      <article className="panel rivers-kpi">
        <div className="rivers-kpi-top"><Leaf size={20} aria-hidden="true" /><InfoTip label="Uso consuntivo" align="end">
          Estimación global de HydroSHEDS (Grill et al. 2019): porcentaje del caudal natural que se consume (riego, ciudades, industria). Un valor bajo indica que la extracción conocida es pequeña frente al río.</InfoTip></div>
        <strong>{number(useMax, 1)} %</strong>
        <span>del caudal se consume según HydroSHEDS</span>
        <small>Valor máximo entre los tramos</small>
      </article>
    </div>

    <section className="panel rivers-flow" aria-labelledby="rivers-flow-title">
      <div className="mission-chart-heading">
        <div><h2 id="rivers-flow-title" className="with-info">El viaje del agua
          <InfoTip label="El viaje del agua" align="start">Cada tarjeta es un tramo del río. El nivel azul muestra cuánta agua visible queda en el cauce hoy frente a {b0}–{b1}. Elige un tramo para ver su evolución año por año.</InfoTip></h2>
          <p>Del Titicaca a la laguna. Toca un tramo para verlo en detalle.</p></div>
        <ul className="rivers-legend" aria-label="Colores de los tramos">{waterLegend.map((item) => <li key={item.label}><i style={{ background: item.css }} />{item.label}</li>)}</ul>
      </div>
      <ol className="rivers-chain">
        <li className="rivers-node source"><MountainSnow size={20} aria-hidden="true" /><b>Lago Titicaca</b><small>fuente</small></li>
        {flow.map((id) => {
          const item = byId.get(id)!;
          const ratio = item.water.base ? Math.min(1.2, (item.water.recent ?? 0) / item.water.base) : null;
          const color = waterTone(item.water.pct).css;
          return <li key={id} className={id === 'M' ? 'rivers-node tributary' : 'rivers-node'}>
            <button type="button" aria-pressed={current.id === id} onClick={() => setReach(id)}
              aria-label={`${id} ${item.name}: ${item.water.pct == null ? 'sin dato' : signed(item.water.pct) + ' % de agua en el cauce'}`}>
              <span className="rivers-level" aria-hidden="true"><i style={{ height: `${(ratio ?? 0) / 1.2 * 100}%`, background: color }} /></span>
              <b>{id === 'M' ? 'Mauri' : id}</b>
              <small>{id === 'M' ? 'afluente desde Perú' : item.name}</small>
              <em style={{ color }}>{item.water.pct == null ? 's/d' : `${signed(item.water.pct)} %`}</em>
            </button>
          </li>;
        })}
        <li className="rivers-node sink"><Waves size={20} aria-hidden="true" /><b>{lake.name.replace(/^Lago /, '')}</b>
          <small>{lake.change_pct == null ? '' : `${signed(lake.change_pct)} % de agua`}</small></li>
      </ol>
    </section>

    <div className="rivers-grid">
      <section className="panel rivers-map-panel" aria-labelledby="rivers-map-title">
        <div className="mission-chart-heading"><div>
          <h2 id="rivers-map-title" className="with-info">Mapa del río
            <InfoTip label="Mapa del río" align="start">El color de cada tramo indica cuánto cambió el agua en su cauce. Los puntos son obras y actividades de OpenStreetMap. Haz clic en un tramo para seleccionarlo.</InfoTip></h2>
          <p>Imagen satelital con los tramos y lo que hay alrededor.</p></div></div>
        <div className="rivers-kind-filter" role="group" aria-label="Mostrar en el mapa">
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
        <h2 id="rivers-works-title" className="with-info">¿Qué hay en el camino?
          <InfoTip label="Obras y actividades" align="end">{(Object.keys(kindInfo) as OsmKind[]).map((kind) => <span key={kind} className="tip-row"><b>{kind}:</b> {kindInfo[kind]}</span>)}</InfoTip></h2>
        <Donut label="Obras y actividades registradas" centerLabel="registros OSM" size={190}
          slices={(Object.keys(kindColors) as OsmKind[]).map((kind) => ({ key: kind, label: kind, value: lake.osm[kind], color: kindColors[kind].css }))} />
        <p className="muted">Fuente: OpenStreetMap. Cerca de Uru Uru muchos “canales” son desagües de la ciudad de Oruro.</p>
      </section>
    </div>

    <section className="panel rivers-reach" aria-labelledby="rivers-reach-title">
      <div className="mission-chart-heading">
        <div><p className="mission-eyebrow">Tramo seleccionado</p>
          <h2 id="rivers-reach-title">{current.id === 'M' ? 'Río Mauri' : `${current.id} · ${current.name}`}</h2>
          <p>{current.km ? `Kilómetros ${current.km[0]} a ${current.km[1]} desde la salida del Titicaca.` : 'Afluente que nace en Perú y se une al Desaguadero en Calacoto.'}</p></div>
        <label><span>Cambiar tramo</span><select value={current.id} onChange={(event) => setReach(event.target.value)}>
          {flow.map((id) => <option key={id} value={id}>{id === 'M' ? 'Mauri' : `${id} · ${byId.get(id)!.name}`}</option>)}
        </select></label>
      </div>
      <div className="rivers-reach-body">
        <div className="rivers-chips">
          <Chip label="Agua en el cauce" value={current.water.pct == null ? 's/d' : `${signed(current.water.pct)} %`} color={waterTone(current.water.pct).css}
            info={`Promedio ${b0}–${b1}: ${number(current.water.base ?? 0)} ha. Promedio ${r0}–${r1}: ${number(current.water.recent ?? 0)} ha.`} />
          <Chip label="Verde en época seca" value={`${signed(current.green.delta ?? 0)} ha`} color="#f7b84b"
            info={`De ${number(current.green.base ?? 0)} a ${number(current.green.recent ?? 0)} ha verdes de junio a octubre a 5 km del río. Incluye bofedales naturales: lo que importa es cuánto crece.`} />
          <Chip label="Cultivos (MapBiomas)" value={current.crops.pct == null ? 's/d' : `${signed(current.crops.pct)} %`} color="#a3e635"
            info={`Superficie agrícola a 5 km del río según MapBiomas: ${number(current.crops.base ?? 0)} → ${number(current.crops.recent ?? 0)} ha.`} />
          <Chip label="Represas y estanques" value={`${signed(current.artificial.delta ?? 0)} ha`} color="#818cf8"
            info="Cambio del agua artificial (represas, reservorios y estanques) a 5 km del río, según MapBiomas Agua." />
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
              <Area dataKey="water" name="Agua en el cauce" type="monotone" stroke="#56c4f5" fill="#56c4f5" fillOpacity={0.22} strokeWidth={2} />
              <Line dataKey="green" name="Verde en época seca" type="monotone" stroke="#f7b84b" strokeWidth={2} dot={false} connectNulls={false} />
              <Line dataKey="greenFilled" name="Año sin imagen (estimado)" type="monotone" stroke="#f7b84b" strokeDasharray="2 3" dot={{ r: 3 }} legendType="none" />
            </ComposedChart>
          </ResponsiveContainer></div>
          <figcaption>Hectáreas por año. La franja clara es el periodo de referencia {b0}–{b1}. 2002 no tiene mosaico Landsat de época seca y se estima.</figcaption>
        </figure>
      </div>
    </section>

    <div className="rivers-diversion-wrap">
      <div className="mission-section-heading">
        <h2 className="with-info">¿Se pierde agua entre un tramo y el siguiente?
          <InfoTip label="Prueba de desvío" align="start">Con los años {b0}–{b1} aprendemos cuánta agua suele tener cada tramo según el de arriba. Después medimos si llega cada vez menos de lo esperado (Mann–Kendall corregido por autocorrelación, p menor a 0,05 y al menos −10 %). Si además crece el verde o hay canales, marcamos un posible desvío.</InfoTip></h2>
        <p>Comparamos el agua que tiene cada tramo con la que debería tener según el tramo de arriba.</p>
      </div>
      <div className="rivers-diversion">
        {pairs.map((pair) => {
          const verdict = verdictTone[pair.verdict] ?? verdictTone['Sin pérdida significativa'];
          const mini = data.years.map((year, index) => ({ year, expected: pair.expected[index], observed: pair.observed[index] }));
          return <article key={pair.to} className={`panel rivers-pair ${verdict.className}`}>
            <header><b>{pair.from} <ArrowRight size={14} aria-hidden="true" /> {pair.to}</b><span className={`pair-badge ${verdict.className}`}><verdict.Icon size={14} aria-hidden="true" />{pair.verdict}</span></header>
            <p>{pair.to_name}</p>
            <div className="pair-chart" aria-hidden="true"><ResponsiveContainer width="100%" height="100%" minWidth={0}>
              <ComposedChart data={mini} margin={{ top: 4, right: 4, left: 4, bottom: 0 }}>
                <XAxis dataKey="year" hide /><YAxis hide />
                <Line dataKey="expected" stroke="#9fb8bd" strokeDasharray="4 3" dot={false} strokeWidth={1.5} />
                <Line dataKey="observed" stroke="#56c4f5" dot={false} strokeWidth={2} />
              </ComposedChart>
            </ResponsiveContainer></div>
            <dl>
              <div><dt>Agua frente a lo esperado</dt><dd>{pair.missing_pct == null ? 's/d' : `${signed(pair.missing_pct)} %`}</dd></div>
              <div><dt>Verde en seca</dt><dd>{signed(pair.green_delta_ha ?? 0)} ha</dd></div>
              <div><dt>Canales y tomas</dt><dd>{number(pair.canals)}</dd></div>
            </dl>
            <small>p = {pair.p == null ? 's/d' : number(pair.p, 3)} · línea punteada: esperada · línea azul: observada</small>
          </article>;
        })}
      </div>
      <p className="muted">{flagged.length
        ? `Resultado: ${flagged.map((pair) => `${pair.from}→${pair.to} (${pair.verdict.toLowerCase()})`).join(', ')}.`
        : 'Resultado: ningún tramo pierde agua de forma significativa frente al de arriba.'}
        {(t1.water.pct ?? 0) <= -40 && ' La caída ya se ve a la salida del propio Titicaca, lo que apunta al nivel del lago más que a un desvío en el camino.'}
        {' '}Límite: se mide el ancho del agua, no el caudal; un desvío chico puede no notarse. El satélite SWOT (NASA/CNES, desde 2023) permitirá medir caudal.</p>
    </div>

    <section className="panel rivers-changes" aria-labelledby="rivers-changes-title">
      <h2 id="rivers-changes-title" className="with-info">Agua en el cauce, tramo por tramo
        <InfoTip label="Cambio por tramo" align="start">Porcentaje de cambio del agua visible en el cauce: promedio {r0}–{r1} contra {b0}–{b1}. A la izquierda, pérdida; a la derecha, ganancia.</InfoTip></h2>
      <DivergingBars max={100} rows={flow.map((id) => {
        const item = byId.get(id)!;
        return { key: id, label: id === 'M' ? 'Mauri' : id, hint: id === 'M' ? 'afluente' : item.name, value: item.water.pct, color: waterTone(item.water.pct).css };
      })} />
    </section>

    <section className="panel rivers-quality" aria-labelledby="rivers-quality-title">
      <div className="mission-chart-heading">
        <div><h2 id="rivers-quality-title"><ShieldCheck size={22} aria-hidden="true" /> ¿Qué tan confiables son estos datos?</h2>
          <p>Controles automáticos sobre los datos que alimentan esta página. Lo que no pasa se muestra igual.</p></div>
        <div className="rivers-downloads">
          <button type="button" onClick={exportCsv}><Download size={16} aria-hidden="true" /> Descargar tramos (CSV)</button>
          <a className="button-link" href="/api/rivers" download="rio_resumen.json"><Download size={16} aria-hidden="true" /> Datos completos (JSON)</a>
        </div>
      </div>
      <ul className="rivers-checks">{data.quality.map((check) => <li key={check.label} className={!check.ok ? 'fail' : check.warn ? 'warn' : 'ok'}>
        {!check.ok || check.warn ? <AlertTriangle size={18} aria-hidden="true" /> : <CheckCircle2 size={18} aria-hidden="true" />}
        <div><b>{check.label}</b><p>{check.detail}</p></div>
      </li>)}</ul>
      <h3>Fuentes</h3>
      <ul className="rivers-sources">{data.sources.map((source) => <li key={source.name}>
        <a href={source.url} target="_blank" rel="noreferrer">{source.name} <ExternalLink size={13} aria-hidden="true" /></a><span>{source.use}</span>
      </li>)}</ul>
      <details className="rivers-why"><summary>Cómo llegó el modelo a este veredicto</summary>
        <ul>{lake.why.map((reason) => <li key={reason}>{reason}</li>)}</ul></details>
      <p className="muted">Análisis generado el {data.generated}. <Link href={`/?vista=ficha&laguna=${lake.id}`}>Abrir la ficha completa de la laguna <ArrowUpRight size={13} aria-hidden="true" /></Link>
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
