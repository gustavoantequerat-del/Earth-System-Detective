'use client';

import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { ArrowDown, ArrowUpRight, CalendarDays, Download, Flame, Layers, Map as MapIcon, ScanSearch, Search, Table2 } from 'lucide-react';
import { api, downloadCsv, firstSuspect, humanEvidenceStates, methodNames, modelUrl, number, searchKey, signed, states,
  visibleStates, type Method, type Snapshot, type State, type WatchSignal, type WaterBody, type Weekly } from './data';
import { Status, DataTable } from './ui';
import { MissionNav } from './mission-nav';
import { MissionHome } from './mission-home';
import { Guide } from './guide';
import { Alerts, useWatchlist } from './alerts';
import { SourceInventory } from './source-inventory';

const MapView = dynamic(() => import('./map-view'), {
  ssr: false,
  loading: () => <div className="map-frame loading" role="status">Cargando mapa…</div>,
});
const Details = dynamic(() => import('./details').then((module) => module.Details), {
  loading: () => <p className="loading" role="status">Cargando ficha…</p>,
});
const Overview = dynamic(() => import('./overview'), {
  loading: () => <p className="loading" role="status">Cargando el análisis de los lagos…</p>,
});
const Vegetation = dynamic(() => import('./vegetation'), {
  loading: () => <p className="loading" role="status">Cargando vegetación…</p>,
});
const RegionalVegetation = dynamic(() => import('./regional-vegetation'), {
  ssr: false,
  loading: () => <p className="loading" role="status">Cargando el atlas provincial…</p>,
});
const FireHistory = dynamic(() => import('./fire-history'), {
  ssr: false,
  loading: () => <section id="mapa-incendios" className="panel mission-data-panel" tabIndex={-1}>
    <h2>Mapa histórico de focos</h2><p className="loading" role="status">Cargando el mapa…</p>
  </section>,
});
const RecentFires = dynamic(() => import('./environment').then((module) => module.RecentFires));
const lakeViews = {
  mapa: { name: 'Lagos de Bolivia', label: 'Mapa 3D', icon: MapIcon, description: 'Encuentra lagos por nombre, ubícalos en el mapa y mira cuánto cambió su superficie de agua. Las gotas flotantes llevan a los casos con ficha completa.' },
  monitoreo: { name: 'Monitoreo de lagos', label: 'Monitoreo', icon: Table2, description: 'Compara la superficie, el cambio de agua y los diagnósticos de varios lagos en una tabla. Puedes filtrar la lista y descargar los resultados.' },
  ficha: { name: 'Fichas de lagos', label: 'Fichas', icon: ScanSearch, description: 'Cada ficha empieza con un resumen del lago. Debajo encontrarás imágenes de antes y después, datos de agua y clima, y las pruebas del diagnóstico.' },
} as const;
const views = {
  panorama: { name: 'Análisis de los lagos', description: 'Mira cuántos lagos se analizaron, qué diagnósticos se encontraron y qué casos puedes explorar a fondo.' },
  ...lakeViews,
  vigilancia: { name: 'Incendios', description: 'Ubica los focos de calor de Bolivia en el mapa histórico y revisa el reporte semanal guardado alrededor de los lagos.' },
  vegetacion: { name: 'Vegetación', description: 'Explora cómo se relacionaron la lluvia y el verdor en las provincias de Bolivia. En las cuencas de los lagos puedes comparar imágenes y cambios de bosque, cultivos y pasturas.' },
} as const;
type View = keyof typeof views;

function locationFor(view: View, method: Method, body?: string | null) {
  const params = new URLSearchParams();
  if (view !== 'panorama') params.set('vista', view);
  if (method === 'conservative') params.set('metodo', 'conservador');
  if (body) params.set('laguna', body);
  return params.size ? `/?${params}` : '/';
}

export function Dashboard() {
  const router = useRouter();
  const params = useSearchParams();
  const candidate = params.get('vista');
  const view = candidate === 'lagos' ? 'mapa' : candidate === 'incendios' ? 'vigilancia'
    : candidate && Object.hasOwn(views, candidate) ? candidate as View : 'panorama';
  const lakeSection = view === 'mapa' || view === 'monitoreo' || view === 'ficha';
  const requestedMethod: Method = params.get('metodo') === 'conservador' ? 'conservative' : 'balance';
  const selected = params.get('laguna');
  const province = params.get('provincia') ?? undefined;
  const vegetationByLake = params.get('area') === 'lagos' || Boolean(selected);
  const [snapshots, setSnapshots] = useState<Partial<Record<Method, Snapshot>>>({});
  const [weekly, setWeekly] = useState<Weekly>();
  const [error, setError] = useState<{ method: Method; message: string }>();
  const [weeklyError, setWeeklyError] = useState('');
  const [showControls, setShowControls] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [weeklyAttempt, setWeeklyAttempt] = useState(0);
  const method = snapshots.balance?.conservativeAvailable === false ? 'balance' : requestedMethod;
  const watchlist = useWatchlist(method);
  const snapshot = snapshots[method];
  const currentError = error?.method === method ? error.message : undefined;

  useEffect(() => {
    if (snapshots.balance) return;
    const request = new AbortController();
    api<Snapshot>('dashboard', { signal: request.signal })
      .then((balance) => setSnapshots((previous) => ({ ...previous, balance })))
      .catch((error: Error) => {
        if (!request.signal.aborted) setError({ method: requestedMethod, message: error.message });
      });
    return () => request.abort();
  }, [attempt, requestedMethod, snapshots.balance]);

  useEffect(() => {
    if (method !== 'conservative' || !snapshots.balance?.conservativeAvailable || snapshot) return;
    const request = new AbortController();
    api<Snapshot>(modelUrl('dashboard', 'conservative'), { signal: request.signal })
      .then((conservative) => setSnapshots((previous) => ({ ...previous, conservative })))
      .catch((error: Error) => {
        if (!request.signal.aborted) setError({ method: 'conservative', message: error.message });
      });
    return () => request.abort();
  }, [attempt, method, snapshot, snapshots.balance?.conservativeAvailable]);

  useEffect(() => {
    const request = new AbortController();
    api<Weekly>('weekly', { signal: request.signal }).then(setWeekly).catch((error: Error) => {
      if (!request.signal.aborted) setWeeklyError(error.message);
    });
    return () => request.abort();
  }, [weeklyAttempt]);

  const controls = new Set(snapshot?.results.map((body) => body.control_id).filter(Boolean));
  const visible = snapshot?.results.filter((body) => body.body_id === selected || showControls ||
    !controls.has(body.body_id) || humanEvidenceStates.includes(body.state)) ?? [];
  const current = visible.find((body) => body.body_id === selected);
  const mappedLake = current ?? snapshot?.national.find((body) => body.body_id === selected);
  const searchLakes = [...(snapshot?.results ?? []), ...(snapshot?.national ?? [])];
  const vegetationId = snapshot?.results.find((body) => body.body_id === selected)?.body_id
    ?? snapshot?.results.find((body) => body.body_id === 'poopo')?.body_id ?? snapshot?.results[0]?.body_id;
  const links = {
    inicio: locationFor('panorama', method),
    lagos: locationFor('mapa', method, selected),
    incendios: locationFor('vigilancia', method),
    vegetacion: locationFor('vegetacion', method),
  };

  function openDetails(id: string) {
    router.push(locationFor('ficha', method, id));
  }

  function selectBody(id: string | null) {
    router.replace(locationFor(view, method, id), { scroll: false });
  }

  function selectProvince(code?: string) {
    const href = locationFor('vegetacion', method);
    router.replace(code ? `${href}&provincia=${encodeURIComponent(code)}` : href, { scroll: false });
  }

  function openAlert(signal: WatchSignal) {
    if (signal.type === 'incendios') return links.incendios + '#reporte-incendios';
    if (signal.type === 'vegetacion') return locationFor('vegetacion', method, signal.id) + '#vegetation-series';
    return locationFor('ficha', method, signal.id) + '#resumen-ficha';
  }

  return <div className="shell">
    <a className="skip-link" href="#contenido">Ir al contenido</a>
    <MissionNav links={links} active={lakeSection ? 'lagos' : view === 'vigilancia' ? 'incendios' : view === 'vegetacion' ? 'vegetacion' : 'inicio'} />
    <main id="contenido" className={view === 'panorama' ? 'main-content mission-home' : 'main-content mission-subpage'}>
      {view === 'panorama' && <MissionHome lakes={links.lagos} fires={links.incendios} vegetation={links.vegetacion}
        alerts={<Alerts watchlist={watchlist} link={openAlert} />} />}
      {lakeSection && <nav className="lake-nav" aria-label="Explorar lagos">
        {(Object.entries(lakeViews) as [keyof typeof lakeViews, typeof lakeViews[keyof typeof lakeViews]][]).map(([key, { label, icon: Icon }]) =>
          <Link key={key} href={locationFor(key, method, key === 'monitoreo' ? null : selected)} aria-current={key === view ? 'page' : undefined}>
            <Icon size={17} aria-hidden="true" />{label}
          </Link>)}
      </nav>}
      <header className="page-header"><div>
        {view === 'panorama' ? <h2>{views[view].name}</h2> : <h1>{views[view].name}</h1>}
        <p>{views[view].description}</p>
      </div>
        {(view === 'panorama' || lakeSection) && <div className="page-actions">
          {(view === 'panorama' || view === 'mapa' || view === 'ficha') && snapshot && <label className="control-check">
            <input type="checkbox" checked={showControls} onChange={(event) => {
              setShowControls(event.target.checked);
              if (!event.target.checked && current && controls.has(current.body_id) && !humanEvidenceStates.includes(current.state)) {
                selectBody(null);
              }
            }} /> Mostrar lagos de comparación
          </label>}
          {snapshots.balance?.conservativeAvailable && <fieldset className="method-switch">
            <legend>Método de análisis</legend>
            <div>{(Object.keys(methodNames) as Method[]).map((option) => (
              <label key={option}><input type="radio" name="analysis-method" checked={method === option} onChange={() => {
                setError(undefined);
                router.push(locationFor(view, option, selected), { scroll: false });
              }} /><span>{methodNames[option]}</span></label>
            ))}</div>
          </fieldset>}
        </div>}
      </header>
      {currentError && view !== 'vigilancia' && (view !== 'vegetacion' || vegetationByLake) && <div className="notice danger" role="alert">
        <p>{currentError}</p>
        <button type="button" onClick={() => { setError(undefined); setAttempt((value) => value + 1); }}>Reintentar</button>
      </div>}
      {!snapshot && !currentError && view !== 'vigilancia' && (view !== 'vegetacion' || vegetationByLake) && <p className="loading" role="status">Cargando datos del detector…</p>}
      {snapshot?.sample && <p className="notice">Datos ficticios de prueba.</p>}
      {snapshot && method === 'conservative' && (view === 'panorama' || lakeSection) && <p className="notice model-note">
        <span>Modelo conservador aplicado a los casos con análisis completo. <Link href={locationFor('mapa', 'balance')}>Ver el barrido nacional en el mapa.</Link></span>
      </p>}
      {snapshot && view === 'panorama' && <>
        <div className="overview-actions">
          <Link className="button-link primary" href={locationFor('mapa', method)}><MapIcon size={17} aria-hidden="true" /> Abrir mapa 3D <ArrowUpRight size={15} aria-hidden="true" /></Link>
          {method === 'balance' && snapshot.conservativeAvailable && <Link className="button-link" href={locationFor('mapa', 'conservative')}>
            Ver modelo conservador en el mapa
          </Link>}
        </div>
        <Overview snapshot={snapshot} method={method} bodies={visible} weekly={weekly} openDetails={openDetails} />
      </>}
      {snapshot && view === 'mapa' && <><MapView key={method} method={method} snapshot={snapshot} bodies={visible} searchBodies={searchLakes}
        selected={mappedLake} select={selectBody} openDetails={openDetails} alerts={watchlist.data?.signals} />
        <Alerts key={view} watchlist={watchlist} link={openAlert} category="agua" /></>}
      {snapshot && view === 'monitoreo' && <><Alerts key={view} watchlist={watchlist} link={openAlert} category="agua" />
        <Monitor key={method} method={method} snapshot={snapshot} weekly={weekly} openDetails={openDetails} /></>}
      {snapshot && view === 'ficha' && (visible.length ? <Details key={method} method={method} bodies={visible} id={current?.body_id ?? visible[0].body_id}
        select={selectBody} back={() => router.push(locationFor('mapa', method, current?.body_id ?? visible[0].body_id))}
        alerts={<Alerts key={view} watchlist={watchlist} link={openAlert} category="agua" bodyId={current?.body_id ?? visible[0].body_id} />} />
        : <p className="notice">No hay cuerpos de agua disponibles.</p>)}
      {view === 'vegetacion' && <>
        <nav className="lake-nav vegetation-nav" aria-label="Explorar vegetación">
          <Link href={locationFor('vegetacion', method)} aria-current={vegetationByLake ? undefined : 'page'}>Por provincia</Link>
          <Link href={locationFor('vegetacion', method, selected) + '&area=lagos'} aria-current={vegetationByLake ? 'page' : undefined}>Cuencas de lagos</Link>
        </nav>
        {vegetationByLake ? snapshot && (vegetationId
          ? <><Alerts key={view} watchlist={watchlist} link={openAlert} category="vegetacion" />
            <Vegetation bodies={snapshot.results} id={vegetationId} method={method} select={selectBody} details={locationFor('ficha', method, vegetationId)} /></>
          : <p className="notice">No hay cuerpos de agua con datos de vegetación.</p>)
          : <RegionalVegetation selected={province} select={selectProvince} />}
      </>}
      {view === 'vigilancia' && <>
        <nav className="section-jump" aria-label="Qué encontrarás en Incendios">
          <a className="button-link" href="#mapa-incendios"><MapIcon size={17} aria-hidden="true" /> Mapa histórico <ArrowDown size={15} aria-hidden="true" /></a>
          <a className="button-link" href="#reporte-incendios"><CalendarDays size={17} aria-hidden="true" /> Reporte por lagos <ArrowDown size={15} aria-hidden="true" /></a>
        </nav>
        <Alerts key={view} watchlist={watchlist} link={openAlert} category="incendios" />
        <FireHistory />
        <RecentFires />
        <section id="reporte-incendios" className="fire-weekly" aria-labelledby="fire-weekly-title" tabIndex={-1}>
          <div className="mission-section-heading">
            <h2 id="fire-weekly-title">Reporte semanal por lago</h2>
            <p>Compara la semana guardada con lo que suele detectarse en la misma época del año.</p>
          </div>
          {weeklyError ? <div className="notice danger" role="alert">{weeklyError}
            <button type="button" onClick={() => { setWeeklyError(''); setWeeklyAttempt((value) => value + 1); }}>Reintentar</button>
          </div> : <Watch weekly={weekly} map={links.lagos} />}
        </section>
      </>}
      {view === 'panorama' && <SourceInventory />}
      <footer>Los diagnósticos se basan en coincidencia y consistencia estadística. Fuentes: Landsat, NASA POWER y FIRMS, NOAA, JRC, MapBiomas Bolivia, Hansen, HydroBASINS y OpenStreetMap.</footer>
    </main>
    <Guide key={view === 'vegetacion' && !vegetationByLake ? 'provincias' : view}
      view={view === 'vegetacion' && !vegetationByLake ? 'provincias' : view} />
  </div>;
}

function Monitor({ snapshot, weekly, method, openDetails }: { snapshot: Snapshot; weekly?: Weekly; method: Method; openDetails: (id: string) => void }) {
  const [search, setSearch] = useState('');
  const [state, setState] = useState<State | ''>('');
  const [mode, setMode] = useState('');
  const [minimum, setMinimum] = useState('');
  const query = searchKey(search);
  const controls = new Set(snapshot.results.map((body) => body.control_id).filter(Boolean));
  const stateList = visibleStates(method, [...snapshot.results, ...snapshot.national]);
  const fires = new Map(weekly?.report?.rows.map((body) => [body.body_id, body]));
  const rows = [
    ...snapshot.results.map((body) => ({ body, mode: controls.has(body.body_id) && !humanEvidenceStates.includes(body.state) ? 'Gemela de control' : 'Completo' })),
    ...snapshot.national.map((body) => ({ body, mode: 'Barrido nacional' })),
  ].filter((row) => (!state || row.body.state === state) && (!mode || row.mode === mode) &&
    searchKey(row.body.name).includes(query) &&
    (!Number(minimum) || row.body.trend.change_pct <= -Math.abs(Number(minimum))))
    .sort((a, b) => stateList.indexOf(a.body.state) - stateList.indexOf(b.body.state) || a.body.trend.change_pct - b.body.trend.change_pct)
    .map(({ body, mode }) => {
      const fire = fires.get(body.body_id);
      const share = body.climate_share == null || body.trend.change_pct > -10 ? null
        : Math.round(100 * Math.max(-1, Math.min(2, body.climate_share)));
      return {
        body, mode, share, suspect: firstSuspect(body),
        fire: fire ? `${fire.alerta ? 'Alerta · ' : ''}${Object.entries(fire.areas).map(([area, a]) => `${area}: ${a.focos}`).join(' · ')}` : '',
      };
    });

  return <>
    <div className="toolbar panel" id="filtros-monitoreo" tabIndex={-1}>
      <label><span><Search size={15} aria-hidden="true" /> Buscar por nombre</span><input type="search" placeholder="Nombre del lago o laguna"
        value={search} onChange={(event) => setSearch(event.target.value)} /></label>
      <label>Estado<select value={state} onChange={(event) => setState(event.target.value as State | '')}><option value="">Todos</option>
        {stateList.map((state) => <option key={state} value={state}>{states[state].label}</option>)}</select></label>
      <label>Análisis<select value={mode} onChange={(event) => setMode(event.target.value)}><option value="">Todos</option>
        <option>Completo</option><option>Gemela de control</option>{snapshot.national.length > 0 && <option>Barrido nacional</option>}</select></label>
      <label>Pérdida mínima (%)<input type="number" min="0" value={minimum} onChange={(event) => setMinimum(event.target.value)} placeholder="0" /></label>
    </div>
    <div className="section-bar" id="datos-monitoreo" tabIndex={-1}><p>{rows.length} {rows.length === 1 ? 'cuerpo de agua' : 'cuerpos de agua'}</p>
      <button type="button" disabled={!rows.length} onClick={() => downloadCsv(rows.map(({ body, mode, share, fire, suspect }) => ({
        'Cuerpo de agua': body.name, Estado: states[body.state].label, 'Análisis': mode, Confianza: body.confidence,
        Pruebas: `${body.n_pass}/3`, 'Cambio %': body.trend.change_pct, 'Clima explica %': share,
        'Sospechoso principal': suspect?.label ?? '', Evidencia: suspect?.evidence ?? '',
        'Motivos': body.why?.join(' ') ?? '',
        'Incendios 7 días': fire, Calidad: body.data_quality?.level ?? '',
        'Superficie (ha)': body.ha ?? body.baseline_mean_ha ?? null, Latitud: body.lat, Longitud: body.lon,
      })))}><Download size={16} aria-hidden="true" /> Descargar CSV</button>
    </div>
    {!!rows.length && <div className="table-wrap"><table>
      <thead><tr>{['Cuerpo de agua', 'Estado', 'Análisis', 'Cambio', 'Confianza', 'Clima explica', 'Sospechoso principal',
        'Calidad', 'Incendios 7 días', 'Superficie (ha)'].map((label) => <th scope="col" key={label}>{label}</th>)}</tr></thead>
      <tbody>{rows.map(({ body, mode, share, fire, suspect }) => <tr key={body.body_id}>
        <td>{mode === 'Barrido nacional' ? body.name : <button className="table-link" type="button" onClick={() => openDetails(body.body_id)}>
          {body.name}<ArrowUpRight size={14} aria-hidden="true" /></button>}</td><td><Status state={body.state} /></td>
        <td>{mode}</td><td>{signed(body.trend.change_pct)}%</td><td>{body.confidence} · {body.n_pass}/3</td>
        <td>{share == null ? '—' : `${share}%`}</td><td>{suspect?.label ?? '—'}{suspect?.evidence && <small>{suspect.evidence}</small>}</td>
        <td>{body.data_quality?.level ?? (body.quality ? (body.quality.eligible ? 'Elegible' : 'Poca calidad') : '—')}</td>
        <td>{fire || '—'}</td><td>{number(body.ha ?? body.baseline_mean_ha ?? 0)}</td>
      </tr>)}</tbody>
    </table></div>}
  </>;
}

function Watch({ weekly, map }: { weekly?: Weekly; map: string }) {
  const [area, setArea] = useState('cuenca');
  if (!weekly) return <p className="loading" role="status">Cargando vigilancia semanal…</p>;
  const report = weekly.report;
  const alerts = report?.rows.filter((entry) => entry.alerta).length ?? 0;
  const counts = report?.rows.flatMap((row) => row.areas[area] ? [{ name: row.name, ...row.areas[area] }] : []) ?? [];
  const scale = Math.max(1, ...counts.map(({ focos, normal }) => Math.max(focos, normal)));
  const drill = Boolean(report?.notified.toLowerCase().includes('simulacro'));
  const date = report ? new Intl.DateTimeFormat('es-BO', { dateStyle: 'long', timeZone: 'UTC' }).format(new Date(report.week_end + 'T00:00:00Z')) : '';
  return <>
    {report ? <>
      <div className="fire-week-status panel"><Flame size={26} aria-hidden="true" /><div>
        <span className="mission-eyebrow">{drill ? 'Simulacro · reporte guardado' : 'Reporte guardado'}</span>
        <strong>{alerts ? `${alerts} ${alerts === 1 ? 'lago con alerta' : 'lagos con alerta'}` : 'Sin alertas en esta semana'}</strong>
        <p>Semana que terminó el {date}.</p>
        {drill && <p>El reporte se ejecutó como prueba, sin enviar avisos.</p>}
        <details><summary>Datos del reporte</summary>
          <p>Revisado el {report.checked_at.replace('T', ' ').slice(0, 16)}. Estado del envío: {report.notified}.</p>
        </details>
      </div></div>
      <section className="panel mission-data-panel">
        <div className="mission-chart-heading">
          <div><h3>Focos térmicos por lago</h3><p>Elige si quieres ver solo los alrededores del lago o toda la cuenca que le aporta agua.</p></div>
          <label><span id="fire-area-label">Área</span><select aria-labelledby="fire-area-label"
            value={area} onChange={(event) => setArea(event.target.value)}>
            <option value="cuenca">Toda la cuenca</option><option value="cerca">Cerca de la laguna</option>
          </select></label>
        </div>
        <div className="mission-fire-key"><span><i /> Semana del reporte</span><span><i /> Promedio histórico</span></div>
        {counts.length ? <ul className="mission-fire-chart">
          {counts.map(({ name, focos, normal, alerta }) => <li key={name}><strong>{name}{alerta && <small className="fire-alert-tag">Alerta</small>}</strong>
            <div aria-label={`${focos} focos esta semana y ${number(normal, 1)} de promedio`}>
              <div><i style={{ width: `${focos / scale * 100}%` }} /><b>{number(focos)}</b></div>
              <div><i style={{ width: `${normal / scale * 100}%` }} /><b>{number(normal, 1)}</b></div>
            </div>
          </li>)}
        </ul> : <p className="notice">El reporte no incluye focos para esta área.</p>}
        <Link className="button-link" href={map}>Explorar lagos en el mapa <ArrowUpRight size={16} aria-hidden="true" /></Link>
      </section>
      <details className="panel fire-report-details">
        <summary>Ver tabla del reporte</summary>
        <DataTable rows={report.rows.flatMap((body) => Object.entries(body.areas).map(([area, item]) => ({
        'Cuerpo de agua': body.name, Estado: states[body.state].label, Área: area === 'cerca' ? 'Cerca de la laguna' : 'Toda la cuenca',
        'Focos esta semana': item.focos, 'Normal para esta semana': item.normal, Alerta: item.alerta ? 'Sí' : 'No',
        })))} />
      </details>
      <p className="muted">Referencia: la misma semana de los cinco años anteriores. El sistema marca alerta en un lago en riesgo si detecta 5 focos o más y al menos el doble de lo habitual.</p>
    </> : <p className="notice">Aún no se ha generado un reporte de incendios.</p>}
    <details className="panel fire-report-details">
      <summary><Layers size={17} aria-hidden="true" /> Historial de reportes</summary>
      <DataTable rows={weekly.history} />
    </details>
  </>;
}
