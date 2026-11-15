'use client';

import { useEffect, useMemo, useState } from 'react';
import DeckGL from '@deck.gl/react';
import { FlyToInterpolator, type Layer, type Position } from '@deck.gl/core';
import { TerrainLayer } from '@deck.gl/geo-layers';
import { ColumnLayer, IconLayer, ScatterplotLayer, TextLayer } from '@deck.gl/layers';
import { ArrowDown, ArrowUpRight, Bell, CircleHelp, Droplet, Layers, LocateFixed, Mountain } from 'lucide-react';
import { api, diagnosisMeaning, firstSuspect, signed, states, visibleStates, waterChange,
  type BodyDetail, type Method, type Place, type Snapshot, type State, type WatchSignal, type WaterBody } from './data';
import { LakeSearch } from './lake-search';
import { lakeMarker } from './lake-marker';
import { Status } from './ui';

const esri = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
const terrain = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png';
const country = { longitude: -64.6, latitude: -16.6, zoom: 5.4, pitch: 40, bearing: 0 };
const placeColors: Record<string, [number, number, number]> = {
  'Mina o cantera': [255, 61, 102], Industria: [221, 100, 255],
  'Ciudad o pueblo': [255, 214, 71], 'Represa o canal': [57, 206, 248],
};
type Mode = 'esri' | 'water' | 'landsat';
type Elevation = { lat: number; lon: number; elevation: number | null };
type Point = { name: string; position: Position; color: [number, number, number]; description: string; radius: number };
type LakePoint = Point & { body: WaterBody };
type Column = LakePoint & { loss: number; iconPosition: Position };

const heightKey = (point: { lat: number; lon: number }) => `${point.lat},${point.lon}`;
const estimatedElevation = ({ lat, lon }: { lat: number; lon: number }) => lon < -65.6 && lat < -14.5 ? 4100 : 650;
const rgb = (state: State): [number, number, number] => [...states[state].rgb];

export default function MapView({ snapshot, method, bodies, searchBodies, selected, select, openDetails, alerts }: {
  snapshot: Snapshot; method: Method; bodies: WaterBody[]; searchBodies: WaterBody[]; selected?: WaterBody;
  select: (id: string | null) => void; openDetails: (id: string) => void;
  alerts?: WatchSignal[];
}) {
  const [mode, setMode] = useState<Mode>('esri');
  const [year, setYear] = useState(2024);
  const [fires, setFires] = useState(false);
  const [national, setNational] = useState(snapshot.national.length > 0);
  const [artificial, setArtificial] = useState(Boolean(snapshot.artificial?.points.length));
  const [textureResult, setTextureResult] = useState<{ key: string; url?: string; error?: string }>();
  const [bodyElevations, setBodyElevations] = useState<Elevation[]>([]);
  const [local, setLocal] = useState<{ id: string; places: Place[]; elevations: Elevation[] }>();
  const [gpuError, setGpuError] = useState(false);
  const [camera, setCamera] = useState<{ flat: boolean }>({ flat: false });
  const [explained, setExplained] = useState<State>();
  const icons = useMemo(() => new Map((Object.keys(states) as State[]).map((state) =>
    [state, { default: lakeMarker(rgb(state), false), active: lakeMarker(rgb(state), true) }])), []);
  const selectedId = selected?.body_id;
  const waterAlerts = new Map(alerts?.filter((signal) => signal.type === 'agua').map((signal) => [signal.id, signal]));
  const selectedAlert = selectedId ? waterAlerts.get(selectedId) : undefined;
  const complete = selectedId ? bodies.some((body) => body.body_id === selectedId) : false;
  const textureKey = `${mode}:${year}:${fires}`;
  const activeTexture = textureResult?.key === textureKey ? textureResult : undefined;

  useEffect(() => {
    const request = new AbortController();
    api<Elevation[]>('map/elevation', { signal: request.signal }).then(setBodyElevations).catch(() => {});
    return () => request.abort();
  }, []);

  useEffect(() => {
    if (!selectedId || !complete) return;
    const request = new AbortController();
    const options = { signal: request.signal };
    api<BodyDetail>(`bodies/${selectedId}`, options).then(({ places }) => {
      setLocal({ id: selectedId, places, elevations: [] });
      if (places.length) {
        api<Elevation[]>(`map/elevation?body=${selectedId}`, options)
          .then((elevations) => setLocal({ id: selectedId, places, elevations })).catch(() => {});
      }
    }).catch(() => {});
    return () => request.abort();
  }, [selectedId, complete]);

  useEffect(() => {
    if (mode === 'esri') return;
    const request = new AbortController();
    api<{ url: string }>(`map/texture?mode=${mode}&year=${year}&fires=${fires}`, { signal: request.signal })
      .then(({ url }) => setTextureResult({ key: textureKey, url }))
      .catch((error: Error) => {
        if (!request.signal.aborted) setTextureResult({ key: textureKey, error: error.message });
      });
    return () => request.abort();
  }, [mode, year, fires, textureKey]);

  const view = useMemo(() => ({
    ...(selected ? { latitude: selected.lat, longitude: selected.lon, zoom: 9.3, pitch: 60, bearing: -20 } : country),
    ...(camera.flat ? { pitch: 0, bearing: 0 } : {}),
    transitionInterpolator: new FlyToInterpolator(),
    transitionDuration: 950,
  }), [selected, camera]);
  const heights = new Map([...bodyElevations, ...(local?.id === selectedId ? local?.elevations ?? [] : [])]
    .map((item) => [heightKey(item), item.elevation]));
  const z = (point: { lat: number; lon: number }) => heights.get(heightKey(point)) ?? estimatedElevation(point);
  const elevationScale = selected ? 15 : 900;
  const columns: Column[] = bodies.map((body) => {
    const loss = Math.max(0, -body.trend.change_pct) + 5;
    const ground = z(body) + 30;
    return {
      body, name: body.name, position: [body.lon, body.lat, ground], color: rgb(body.state),
      iconPosition: [body.lon, body.lat, ground + loss * elevationScale],
      description: 'Análisis completo', radius: selected ? 450 : 12000, loss,
    };
  });
  const flagged = columns.filter(({ body }) => waterAlerts.has(body.body_id));
  const nationalPoints: LakePoint[] = (national ? snapshot.national : snapshot.national.filter((body) => body.body_id === selectedId)).map((body) => ({
    body, name: body.name, position: [body.lon, body.lat, z(body)], color: rgb(body.state),
    description: 'Barrido nacional · diagnóstico preliminar',
    radius: body.body_id === selectedId ? 1900 : 1500 + 60 * Math.sqrt(body.ha ?? 0),
  }));
  const artificialPoints: Point[] = (artificial ? snapshot.artificial?.points ?? [] : []).map((point) => ({
    name: point.tipo, position: [point.lon, point.lat, z(point)], color: [0, 245, 255],
    description: `Agua artificial · MapBiomas ${snapshot.artificial?.year}`, radius: Math.max(Math.sqrt(point.ha * 10000 / Math.PI), 250),
  }));
  const places: Point[] = (local && local.id === selectedId ? local.places : []).slice(0, 30).map((place) => ({
    name: place.name || place.kind, position: [place.lon, place.lat, z(place) + 150],
    color: placeColors[place.kind] ?? [255, 255, 255], description: `${place.kind} · a ${place.dist_km} km`, radius: 400,
  }));
  const layers: Layer[] = [
    new TerrainLayer({ id: 'relieve', elevationData: terrain, texture: activeTexture?.url ?? esri,
      elevationDecoder: { rScaler: 256, gScaler: 1, bScaler: 1 / 256, offset: -32768 }, maxZoom: 13 }),
    new ColumnLayer<Column>({ id: 'alert-platforms', data: flagged, getPosition: (p) => [
      p.body.lon, p.body.lat, (p.position[2] ?? 0) + 110,
    ], radius: selected ? 1050 : 22500, diskResolution: 32, extruded: !camera.flat,
    getElevation: selected ? 100 : 1650, getFillColor: (p) => waterAlerts.get(p.body.body_id)?.level === 'prioridad'
      ? [255, 136, 62, 200] : [187, 225, 108, 170], pickable: false }),
    new ScatterplotLayer<LakePoint>({ id: 'barrido', data: nationalPoints, getPosition: (p) => p.position,
      getRadius: (p) => p.radius, getFillColor: (p) => p.color, radiusMinPixels: 5, radiusMaxPixels: 18,
      stroked: true, getLineColor: (p) => p.body.body_id === selectedId ? [228, 255, 116] : [255, 255, 255],
      lineWidthMinPixels: 1.4, pickable: true, autoHighlight: true,
      onClick: ({ object }) => { if (object) select(object.body.body_id); } }),
    new ScatterplotLayer<Point>({ id: 'artificial', data: artificialPoints, getPosition: (p) => p.position,
      getRadius: (p) => p.radius, getFillColor: (p) => p.color, radiusMinPixels: 2, radiusMaxPixels: 14, pickable: true }),
    new ColumnLayer<Column>({ id: 'cuerpos', data: columns, getPosition: (p) => p.position,
      getFillColor: (p) => p.color, getElevation: (p) => p.loss, elevationScale,
      radius: selected ? 450 : 12000, pickable: true, autoHighlight: true, extruded: true,
      onClick: ({ object }) => { if (object) select(object.body.body_id); } }),
    new ScatterplotLayer<Point>({ id: 'alrededores', data: places, getPosition: (p) => p.position,
      getRadius: (p) => p.radius, getFillColor: (p) => p.color, radiusMinPixels: 6, pickable: true }),
    new IconLayer<Column>({ id: 'lake-markers', data: columns, billboard: true, pickable: true, alphaCutoff: .1,
      getPosition: (p) => p.iconPosition, getSize: (p) => p.body.body_id === selectedId ? 56 : 42,
      getIcon: (p) => icons.get(p.body.state)![p.body.body_id === selectedId ? 'active' : 'default'],
      parameters: { depthCompare: 'always', depthWriteEnabled: false },
      onClick: ({ object }) => { if (object) select(object.body.body_id); } }),
    new ScatterplotLayer<Column>({ id: 'alert-orbits', data: flagged, getPosition: (p) => p.iconPosition,
      radiusUnits: 'pixels', getRadius: 11, getPixelOffset: [0, -1], filled: false, stroked: true, lineWidthMinPixels: 3,
      getLineColor: (p) => waterAlerts.get(p.body.body_id)?.level === 'prioridad' ? [255, 169, 102] : [224, 255, 121],
      parameters: { depthCompare: 'always', depthWriteEnabled: false }, pickable: false }),
    new TextLayer<Column>({ id: 'etiquetas', data: selected ? columns.filter((p) => p.body.body_id === selectedId) : columns,
      getPosition: (p) => p.iconPosition,
      getText: (p) => p.name.split(' (')[0], getColor: [240, 248, 249], getSize: 13, fontWeight: 700,
      getPixelOffset: [0, 14], background: true, getBackgroundColor: [10, 19, 25, 228], backgroundPadding: [7, 4],
      parameters: { depthCompare: 'always', depthWriteEnabled: false },
      fontFamily: 'Inter, sans-serif', fontSettings: { sdf: true }, characterSet: 'auto', billboard: true, pickable: true,
      onClick: ({ object }) => { if (object) select(object.body.body_id); } }),
  ];
  const counts = [...bodies, ...(national ? snapshot.national : [])].reduce<Partial<Record<State, number>>>((total, body) => {
    total[body.state] = (total[body.state] ?? 0) + 1;
    return total;
  }, {});
  const mapStates = visibleStates(method, [...bodies, ...(national ? snapshot.national : [])]);
  const priority = [...bodies].sort((a, b) => mapStates.indexOf(a.state) - mapStates.indexOf(b.state) ||
    a.trend.change_pct - b.trend.change_pct);
  const suspect = selected && firstSuspect(selected);

  return <>
    <div className="panel map-discover">
      <LakeSearch id="buscar-lago" bodies={searchBodies} onSelect={select} />
      <div className="map-discover-help">
        <p><CircleHelp size={18} aria-hidden="true" /> Pasa el mouse por una gota o un punto para leer su diagnóstico. En el celular, toca el marcador.</p>
        {!!waterAlerts.size && <a href="#alertas"><Bell size={17} aria-hidden="true" /> {waterAlerts.size} alertas de agua <ArrowDown size={15} aria-hidden="true" /></a>}
      </div>
    </div>
    <div className="map-workspace">
      <section id="mapa-lagos" aria-label="Mapa de cuerpos de agua" className="map-panel panel" tabIndex={-1}>
        <div className="map-toolbar">
          <div className="camera-switch" role="group" aria-label="Perspectiva del mapa">
            <button type="button" aria-pressed={!camera.flat} onClick={() => setCamera({ flat: false })}>
              <Mountain size={16} aria-hidden="true" /> 3D
            </button>
            <button type="button" aria-pressed={camera.flat} onClick={() => setCamera({ flat: true })}>2D</button>
          </div>
          <button className="map-reset" type="button" onClick={() => { select(null); setCamera({ flat: camera.flat }); }}>
            <LocateFixed size={16} aria-hidden="true" /> Vista de Bolivia
          </button>
        </div>
        {mode !== 'esri' && !activeTexture && <p role="status" className="map-notice">Cargando capa de Earth Engine…</p>}
        {activeTexture?.error && <p role="alert" className="map-notice">{activeTexture.error} Se muestra el fondo satelital de Esri.</p>}
        <div className="map-frame">
          {!gpuError ? <DeckGL initialViewState={view} controller={{ dragRotate: !camera.flat, touchRotate: !camera.flat }} layers={layers}
            onError={(error) => { if (/webgl|device|context/i.test(error.message)) setGpuError(true); }}
            getTooltip={({ object }: { object?: Point | LakePoint }) => {
              if (!object) return null;
              const body = 'body' in object ? object.body : undefined;
              const alert = body ? waterAlerts.get(body.body_id) : undefined;
              return { className: 'mission-map-tooltip', text: body ? [
                object.name, states[body.state].label + ' · ' + waterChange(body.trend.change_pct),
                alert ? `${alert.level === 'prioridad' ? 'Prioridad alta' : 'En seguimiento'} · ${alert.from}–${alert.to}` : '',
                diagnosisMeaning[body.state], object.description,
              ].filter(Boolean).join('\n') : `${object.name}\n${object.description}` };
            }} />
            : <p className="map-notice" role="status">El navegador no pudo iniciar WebGL. Puedes elegir un cuerpo de agua en la lista.</p>}
          <div className="attribution">{mode === 'esri' || !activeTexture?.url ? 'Esri World Imagery' : 'Google Earth Engine'} · AWS Terrain Tiles</div>
        </div>
        <div className="map-footer">
          <span><Droplet size={16} aria-hidden="true" /> Gota flotante: lago con ficha completa</span>
          <span><i className="legend-column" aria-hidden="true" /> Más altura indica mayor pérdida de agua</span>
          {national && <span><i className="legend-national" aria-hidden="true" /> Laguna del barrido nacional</span>}
          {artificial && <span><i className="legend-artificial" aria-hidden="true" /> Agua artificial</span>}
          {!!flagged.length && <span><i className="legend-alert" aria-hidden="true" /> Aro naranja: prioridad alta · verde: seguimiento</span>}
        </div>
      </section>

      <aside className="map-sidebar" aria-label="Controles del mapa">
        <section id="capas-lagos" className="panel overview-panel map-layers" tabIndex={-1}>
          <h2><Layers size={18} aria-hidden="true" /> Capas</h2>
          <label>Fondo del mapa<select value={mode} onChange={(event) => setMode(event.target.value as Mode)}>
            <option value="esri">Satélite actual (Esri)</option>
            {snapshot.liveMap && <><option value="water">Agua natural y artificial</option>
              <option value="landsat">Landsat + agua</option></>}
          </select></label>
          {mode !== 'esri' && <>
            <label>Año <select value={year} onChange={(event) => setYear(Number(event.target.value))}>
              {Array.from({ length: 41 }, (_, index) => 2025 - index).map((year) => <option key={year}>{year}</option>)}
            </select></label>
            <label className="check-inline"><input type="checkbox" checked={fires} onChange={(event) => setFires(event.target.checked)} /> Focos FIRMS (7 días)</label>
          </>}
          {!!snapshot.national.length && <label className="check-inline"><input type="checkbox" checked={national} onChange={(event) => setNational(event.target.checked)} /> Barrido nacional ({snapshot.national.length})</label>}
          {!!snapshot.artificial?.points.length && <label className="check-inline"><input type="checkbox" checked={artificial} onChange={(event) => setArtificial(event.target.checked)} /> Agua artificial</label>}
        </section>
        <section className="panel overview-panel" aria-label="Explorar cuerpos de agua">
          <h2>{selected?.name ?? 'Lagos con ficha'}</h2>
          <label htmlFor="lake-shortlist">Elegir un lago con ficha<select id="lake-shortlist" value={complete ? selectedId : ''} onChange={(event) => select(event.target.value || null)}>
            <option value="">Seleccionar cuerpo de agua</option>
            {bodies.map((body) => <option key={body.body_id} value={body.body_id}>{body.name}</option>)}
          </select></label>
          {selected && <div className="map-selection">
            <div><Status state={selected.state} /><strong>{waterChange(selected.trend.change_pct)}</strong></div>
            <p>{diagnosisMeaning[selected.state]}</p>
            {selectedAlert && <p className="map-alert-summary"><Bell size={17} aria-hidden="true" /> {selectedAlert.level === 'prioridad' ? 'Prioridad alta' : 'En seguimiento'}
              {' · '}{selectedAlert.from}–{selectedAlert.to}<a href="#alertas">Ver criterio</a></p>}
            {suspect && <p className="muted">{suspect.label} · {suspect.evidence}</p>}
            {!!selected.why?.length && <ul className="muted">{selected.why.slice(0, 3).map((reason) => <li key={reason}>{reason}</li>)}</ul>}
            {complete ? <button type="button" className="primary" onClick={() => openDetails(selected.body_id)}>Abrir ficha <ArrowUpRight size={16} aria-hidden="true" /></button>
              : <p className="muted">Este lago forma parte del barrido nacional. Su diagnóstico es preliminar.</p>}
          </div>}
          <ul className="priority-list">{priority.map((body) => <li key={body.body_id}>
            <button type="button" aria-pressed={selectedId === body.body_id} onClick={() => select(body.body_id)}>
              <span>{body.name.split(' (')[0]}</span><strong>{signed(body.trend.change_pct)}%</strong>
            </button>
          </li>)}</ul>
        </section>
      </aside>
    </div>
    <section id="diagnosticos-map" className="map-verdicts" aria-label="Diagnósticos visibles" tabIndex={-1}>
      <h2>Diagnósticos visibles</h2>
      <p className="muted">Acércate a una categoría o selecciónala para entender qué significa.</p>
      <div className="status-grid">{mapStates.map((state, index) => <article key={state} className="diagnosis-tile">
        <button type="button" className="panel status-card" aria-expanded={explained === state} aria-describedby={`diagnosis-${index}`}
          onClick={() => setExplained((previous) => previous === state ? undefined : state)}
          onKeyDown={(event) => { if (event.key === 'Escape') setExplained(undefined); }}>
          <strong>{counts[state] ?? 0}</strong><Status state={state} /><CircleHelp size={16} aria-hidden="true" className="diagnosis-info" />
        </button>
        <p id={`diagnosis-${index}`} className="diagnosis-tip" role="tooltip">{diagnosisMeaning[state]}</p>
      </article>)}</div>
    </section>
  </>;
}
