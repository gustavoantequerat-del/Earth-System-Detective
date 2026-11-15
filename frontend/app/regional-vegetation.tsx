'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import DeckGL from '@deck.gl/react';
import type { MapViewState } from '@deck.gl/core';
import { GeoJsonLayer } from '@deck.gl/layers';
import { Box, Leaf, MapPin, Minus, Pause, Play, Plus, RotateCcw } from 'lucide-react';
import { usePlayback } from '../../Naseros/frontend/hooks/usePlayback';
import { api, displayDate, number, signed } from './data';
import { levels, severity, severityFor, type Analysis, type Atlas, type Level, type Region, type RegionLayer,
  type RegionalTimeline, type Verdict } from './regional-vegetation-data';
import { RegionalDetails } from './regional-vegetation-charts';

const cameraHome = { longitude: -64.75, latitude: -16.65, zoom: 4.95, minZoom: 3.6, maxZoom: 11, bearing: 0, pitch: 0 };
const layerNames: Record<RegionLayer, string> = {
  trend: 'Diagnóstico de largo plazo', joint: 'Sequía combinada', rain: 'Diferencia de lluvia', ndvi: 'Diferencia de verdor (NDVI)',
};
const regionsFeatured: { name: string; department: string; priority: Level[] }[] = [
  { name: 'Chaco (Tarija)', department: 'Tarija', priority: ['crisis', 'alert', 'watch'] },
  { name: 'Altiplano (Oruro)', department: 'Oruro', priority: ['stable', 'alert', 'watch'] },
];

function featured(verdicts: Verdict[], department: string, priority: Level[]) {
  const candidates = verdicts.filter((region) => region.adm1_name === department);
  return priority.map((level) => candidates.find((region) => region.level === level)).find(Boolean) ?? candidates[0];
}

function TemporalAtlas({ atlas, selected, select }: { atlas: Atlas; selected?: string; select: (code?: string) => void }) {
  const [view, setView] = useState<MapViewState>(cameraHome);
  const camera = useRef<MapViewState>(cameraHome);
  const [layer, setLayer] = useState<RegionLayer>('trend');
  const [timeline, setTimeline] = useState<RegionalTimeline>();
  const [timelineError, setTimelineError] = useState(false);
  const [retry, setRetry] = useState(0);
  const [detail, setDetail] = useState<{ code: string; analysis?: Analysis; error?: string }>();
  const [detailRetry, setDetailRetry] = useState(0);
  const [gpuError, setGpuError] = useState(false);
  const active = detail?.code === selected ? detail : undefined;
  const { currentDekad, isPlaying, speed, toggle, pause, seek, setSpeed } = usePlayback(timeline?.dates.length ?? 0);
  const flat = view.pitch === 0;
  const byCode = useMemo(() => new Map(atlas.verdicts.map((entry) => [entry.pcode, entry])), [atlas]);
  const date = timeline?.dates[currentDekad];
  const options = useMemo(() => atlas.verdicts.toSorted((a, b) => a.adm1_name.localeCompare(b.adm1_name, 'es') || a.name.localeCompare(b.name, 'es')),
    [atlas.verdicts]);
  const historical = layer === 'trend';

  useEffect(() => {
    if (historical || timeline) return;
    const controller = new AbortController();
    api<RegionalTimeline>('vegetation/timeline', { signal: controller.signal }).then(setTimeline)
      .catch(() => { if (!controller.signal.aborted) setTimelineError(true); });
    return () => controller.abort();
  }, [historical, timeline, retry]);
  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    api<Analysis>(`vegetation/regions/${encodeURIComponent(selected)}`, { signal: controller.signal })
      .then((analysis) => setDetail({ code: selected, analysis }))
      .catch((error: Error) => { if (!controller.signal.aborted) setDetail({ code: selected, error: error.message }); });
    return () => controller.abort();
  }, [selected, detailRetry]);
  useEffect(() => {
    const onHidden = () => { if (document.hidden) pause(); };
    document.addEventListener('visibilitychange', onHidden);
    return () => document.removeEventListener('visibilitychange', onHidden);
  }, [pause]);

  function choose(code?: string) {
    pause();
    select(code);
  }
  function moveCamera(next: MapViewState) {
    camera.current = next;
    setView({ ...next });
  }
  const metrics = (code: string) => {
    const row = timeline?.regions[code];
    const rain = row?.r3q[currentDekad] ?? null;
    const ndvi = row?.viq[currentDekad] ?? null;
    return { rain, ndvi, joint: rain == null || ndvi == null ? null : .6 * rain + .4 * ndvi };
  };
  const layerValue = (region: Region) => {
    const { rain, ndvi, joint } = metrics(region.pcode);
    return layer === 'rain' ? rain : layer === 'ndvi' ? ndvi : joint;
  };
  function color(region: Region) {
    if (historical) return [...levels[byCode.get(region.pcode)?.level ?? 'no_data'].color, 220] as [number, number, number, number];
    const value = layerValue(region);
    const rgb = value == null ? levels.no_data.color : severity[severityFor(value)].color;
    return [...rgb, 222] as [number, number, number, number];
  }
  const layers = [
    new GeoJsonLayer<Region>({
      id: 'provincias-vegetacion', data: atlas.geometry, pickable: true, filled: true, stroked: true, extruded: !flat,
      autoHighlight: true, getFillColor: ({ properties }) => color(properties),
      getLineColor: ({ properties }) => properties.pcode === selected ? [241, 255, 149] : [60, 79, 113, 225],
      getLineWidth: ({ properties }) => properties.pcode === selected ? 3 : 1,
      lineWidthUnits: 'pixels', lineWidthMinPixels: 1,
      getElevation: ({ properties }) => {
        if (historical) return properties.pcode === selected ? 26000 : 4500;
        return Math.min(60, Math.max(0, -(layerValue(properties) ?? 0))) * 1600 + 2500;
      },
      updateTriggers: { getFillColor: [layer, currentDekad, timeline], getElevation: [layer, currentDekad, timeline, selected],
        getLineColor: [selected], getLineWidth: [selected] },
      onClick: ({ object }) => { if (object) choose(object.properties.pcode); },
    }),
  ];

  return <>
    <section id="mapa-provincial" className="panel regional-atlas" tabIndex={-1} aria-labelledby="atlas-title">
      <div className="mission-chart-heading">
        <div><p className="mission-eyebrow"><Leaf size={17} aria-hidden="true" /> Lluvia y vegetación</p>
          <h2 id="atlas-title">Bolivia por provincia</h2>
          <p>{atlas.verdicts.length} provincias · {atlas.from.slice(0, 4)}–{atlas.to.slice(0, 4)}. El NDVI indica el verdor de la vegetación desde satélite.</p></div>
        <div className="camera-switch" role="group" aria-label="Vista del mapa provincial">
          <button type="button" aria-pressed={flat} onClick={() => moveCamera({ ...camera.current, pitch: 0, bearing: 0 })}>2D</button>
          <button type="button" aria-pressed={!flat} onClick={() => moveCamera({ ...camera.current, pitch: 44, bearing: -15 })}><Box size={16} aria-hidden="true" /> 3D</button>
        </div>
      </div>
      <div className="regional-form">
        <label htmlFor="atlas-region"><span id="atlas-region-label">Provincia</span>
          <select id="atlas-region" aria-labelledby="atlas-region-label" value={selected ?? ''} onChange={(event) => choose(event.target.value || undefined)}>
            <option value="">Elige una provincia o toca el mapa</option>
            {options.map((option) => <option key={option.pcode} value={option.pcode}>{option.name} · {option.adm1_name}</option>)}
          </select></label>
        <label htmlFor="atlas-layer"><span id="atlas-layer-label">Qué quieres ver</span>
          <select id="atlas-layer" aria-labelledby="atlas-layer-label" value={layer} onChange={(event) => {
            pause();
            if (timelineError) setRetry((value) => value + 1);
            setTimelineError(false);
            setLayer(event.target.value as RegionLayer);
          }}>
            {Object.entries(layerNames).map(([key, item]) => <option key={key} value={key}>{item}</option>)}
          </select></label>
      </div>
      <div className="regional-shortcuts">{regionsFeatured.map(({ name, department, priority }) => {
        const region = featured(atlas.verdicts, department, priority);
        return <button type="button" key={name} disabled={!region} aria-pressed={!!region && selected === region.pcode}
          onClick={() => choose(region?.pcode)}><MapPin size={16} aria-hidden="true" /> {name}</button>;
      })}{active?.analysis && <a className="button-link" href="#diagnostico-provincial">Ver diagnóstico provincial</a>}</div>
      {!historical && (timelineError ? <div className="notice danger" role="alert">No se pudo cargar la serie temporal.
        <button type="button" onClick={() => { setTimelineError(false); setRetry((value) => value + 1); }}>Reintentar</button></div>
        : !timeline ? <p className="loading" role="status">Cargando la serie por fechas…</p>
          : <div className="regional-playback">
            <button type="button" onClick={toggle}>{isPlaying ? <Pause size={16} aria-hidden="true" /> : <Play size={16} aria-hidden="true" />}
              {isPlaying ? 'Pausar' : 'Reproducir'}</button>
            <label htmlFor="atlas-time"><span>Fecha del mapa</span>
              <input type="range" id="atlas-time" min={0} max={timeline.dates.length - 1} value={currentDekad}
                aria-valuetext={date ? displayDate(date) : ''} onChange={(event) => seek(Number(event.target.value))} /></label>
            <output htmlFor="atlas-time" aria-live={isPlaying ? 'off' : 'polite'}>{date ? displayDate(date) : ''}</output>
            <div className="camera-switch" role="group" aria-label="Velocidad provincial">
              {([1, 2, 4] as const).map((item) => <button key={item} type="button" aria-pressed={speed === item} onClick={() => setSpeed(item)}>{item}×</button>)}
            </div>
          </div>)}
      <div className="regional-map">
        {!gpuError ? <DeckGL initialViewState={view} controller={{ dragRotate: !flat, touchRotate: !flat, scrollZoom: false }}
          onViewStateChange={({ viewState }) => { camera.current = viewState as MapViewState; }}
          onError={(error) => { if (/webgl|device|context/i.test(error.message)) setGpuError(true); }} layers={layers}
          getTooltip={({ object }) => {
            const region = (object?.properties ?? null) as Region | null;
            if (!region) return null;
            const verdict = byCode.get(region.pcode);
            const value = historical ? null : layerValue(region);
            return { className: 'mission-map-tooltip', text: [`${region.name} · ${region.adm1_name}`,
              historical ? (verdict?.verdict ?? 'Sin datos') : value == null ? 'Sin datos para esta fecha' : `${layerNames[layer]} · ${signed(value, 1)} %`,
              historical ? '' : date ? displayDate(date) : ''].filter(Boolean).join('\n') };
          }} />
          : <p className="map-notice">El mapa necesita WebGL. Puedes elegir una provincia arriba.</p>}
        {!gpuError && <div className="fire-map-zoom" role="group" aria-label="Zoom del mapa provincial">
          <button type="button" aria-label="Acercar provincias" onClick={() => moveCamera({ ...camera.current, zoom: Math.min(cameraHome.maxZoom, camera.current.zoom + .7) })}><Plus size={18} aria-hidden="true" /></button>
          <button type="button" aria-label="Alejar provincias" onClick={() => moveCamera({ ...camera.current, zoom: Math.max(cameraHome.minZoom, camera.current.zoom - .7) })}><Minus size={18} aria-hidden="true" /></button>
          <button type="button" aria-label="Restablecer mapa provincial" onClick={() => moveCamera({ ...cameraHome, pitch: flat ? 0 : 44 })}><RotateCcw size={16} aria-hidden="true" /></button>
        </div>}
      </div>
      <div className="regional-legend" aria-label="Leyenda provincial">
        {(historical ? Object.values(levels) : [...Object.values(severity), levels.no_data]).map(({ label, color }) => <span key={label}>
          <i style={{ background: `rgb(${color.join(',')})` }} />{label}</span>)}
      </div>
      <p className="muted">{historical ? 'El color muestra el diagnóstico de lluvia y verdor de toda la serie. En 3D se eleva la provincia seleccionada.'
        : 'Cada fecha representa un periodo de aproximadamente diez días. En 3D, las zonas con mayor déficit se elevan.'}</p>
    </section>
    {selected && !active && <p className="loading" role="status">Cargando diagnóstico provincial…</p>}
    {active?.error && <div className="notice danger" role="alert">{active.error}
      <button type="button" onClick={() => { setDetail(undefined); setDetailRetry((value) => value + 1); }}>Reintentar</button></div>}
    {active?.analysis && <RegionalDetails key={selected} detail={active.analysis} close={() => choose()} />}
    {!selected && <p className="panel watch-empty">Selecciona una provincia para ver tendencias, correlación y los periodos de mayor déficit.</p>}
  </>;
}

export default function RegionalVegetation({ selected, select }: { selected?: string; select: (code?: string) => void }) {
  const [atlas, setAtlas] = useState<Atlas>();
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    api<Atlas>('vegetation/regions', { signal: controller.signal }).then(setAtlas)
      .catch(() => { if (!controller.signal.aborted) setError(true); });
    return () => controller.abort();
  }, [attempt]);
  if (atlas) return <TemporalAtlas atlas={atlas} selected={selected} select={select} />;
  return <section id="mapa-provincial" className="panel regional-atlas" tabIndex={-1}>
    <h2>Bolivia por provincia</h2>
    {error ? <div className="notice danger" role="alert">El atlas provincial no pudo cargarse.
      <button type="button" onClick={() => { setError(false); setAttempt((value) => value + 1); }}>Reintentar</button></div>
      : <p className="loading" role="status">Cargando provincias y diagnósticos…</p>}
  </section>;
}
