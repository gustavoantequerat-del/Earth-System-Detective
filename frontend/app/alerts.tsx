'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowRight, Bell, Droplets, Flame, Leaf } from 'lucide-react';
import { api, displayDate, modelUrl, number, waterChange, type Method, type WatchlistData, type WatchSignal } from './data';
import { Status } from './ui';

const topics = {
  agua: { label: 'Agua', icon: Droplets },
  vegetacion: { label: 'Vegetación', icon: Leaf },
  incendios: { label: 'Incendios', icon: Flame },
} as const;

function Signal({ signal, link }: { signal: WatchSignal; link: string }) {
  const { label, icon: Icon } = topics[signal.type];
  const water = signal.type === 'agua';
  const forest = signal.type === 'vegetacion';
  const metric = water ? waterChange(signal.metric) : forest ? `${number(signal.metric)} ha de bosque perdido` : `${number(signal.metric)} focos de calor`;
  const period = water ? `${signal.from}–${signal.to}` : forest ? signal.to : displayDate(signal.to);
  return <article className={`watch-card watch-${signal.level}`}>
    <div className="watch-card-top"><span><Icon size={19} aria-hidden="true" /> {label}</span>
      <span>{signal.level === 'prioridad' ? 'Prioridad alta' : 'En seguimiento'}</span></div>
    <div><h3>{signal.name}</h3><strong>{metric}</strong>
      <p>{water ? `Promedio de ${period} frente al promedio histórico hasta ${signal.reference ?? 'el fin del periodo base'}.`
        : forest ? `${period} · Mediana de los cinco años anteriores: ${number(signal.reference ?? 0)} ha en la subcuenca local.`
          : `Semana al ${period} · ${number(signal.reference ?? 0, 1)} focos habituales ${signal.area === 'cerca' ? 'cerca del lago' : 'en la cuenca'}.`}</p>
      {water && signal.state && <Status state={signal.state} />}
    </div>
    <div className="watch-card-action"><small>{signal.source}</small>
      <Link href={link}>{water ? 'Ver ficha' : forest ? 'Ver cobertura' : 'Ver reporte'} <ArrowRight size={17} aria-hidden="true" /></Link></div>
  </article>;
}

export function useWatchlist(method: Method) {
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{ method: Method; data?: WatchlistData; error?: boolean }>();
  const data = result?.method === method ? result.data : undefined;
  const failed = result?.method === method && result.error;
  useEffect(() => {
    const request = new AbortController();
    api<WatchlistData>(modelUrl('alerts', method), { signal: request.signal }).then((data) => setResult({ method, data }))
      .catch(() => { if (!request.signal.aborted) setResult({ method, error: true }); });
    return () => request.abort();
  }, [method, attempt]);
  return { data, failed, retry: () => { setResult(undefined); setAttempt((n) => n + 1); } };
}

export function Alerts({ watchlist, link, category, bodyId }: {
  watchlist: ReturnType<typeof useWatchlist>;
  link: (signal: WatchSignal) => string;
  category?: WatchSignal['type'];
  bodyId?: string;
}) {
  const [type, setType] = useState<WatchSignal['type'] | 'all'>('all');
  const [expanded, setExpanded] = useState(false);
  const { data, failed, retry } = watchlist;
  const filter = category ?? type;
  const signals = data?.signals.filter((item) => (filter === 'all' || filter === item.type) && (!bodyId || bodyId === item.id)) ?? [];

  return <section id="alertas" className={`watch-section${category ? ' watch-section-local' : ''}`} aria-labelledby="watch-title" tabIndex={-1}>
    <div className="mission-section-heading">
      <p className="mission-eyebrow"><Bell size={16} aria-hidden="true" /> Observación ambiental</p>
      <h2 id="watch-title">{category ? `Alertas de ${topics[category].label.toLocaleLowerCase('es')}` : 'Alertas para investigar'}</h2>
      <p>{category ? 'Señales del archivo para revisar con los datos de esta sección.' : 'Cambios registrados que merecen revisión. Cada alerta trae el periodo observado y un enlace a los datos.'}</p>
    </div>
    {!data && (failed ? <div className="notice danger" role="alert">Las alertas no pudieron cargarse.
      <button type="button" onClick={retry}>Reintentar</button></div>
      : <p className="loading" role="status">Cargando alertas…</p>)}
    {data && <>
      {!category && <div className="watch-toolbar">
        <div className="camera-switch" role="group" aria-label="Filtrar alertas">
          {(['all', 'agua', 'vegetacion', 'incendios'] as const).map((key) => {
            const count = data.signals.filter((item) => key === 'all' || item.type === key).length;
            return <button type="button" key={key} aria-pressed={type === key} onClick={() => { setType(key); setExpanded(false); }}>
              {key === 'all' ? 'Todas' : topics[key].label} <small>{count}</small></button>;
          })}
        </div>
        <a href="#fuentes-observatorio">Fuentes y cobertura</a>
      </div>}
      {signals.length ? <div className="watch-grid">{signals.slice(0, expanded ? undefined : 3).map((item) =>
        <Signal key={`${item.id}-${item.type}-${item.area ?? ''}`} signal={item} link={link(item)} />)}</div>
        : <p className="panel watch-empty">{data.sample ? 'La copia de prueba no genera alertas.' : filter === 'incendios' && data.weekly?.drill
          ? `El reporte del ${displayDate(data.weekly.date)} fue un simulacro. La comparación está disponible en el reporte semanal.`
          : bodyId ? 'Este caso no alcanzó el umbral de alerta en el archivo disponible.'
            : 'El archivo no contiene alertas de este tipo para los casos analizados.'}</p>}
      {signals.length > 3 && <button type="button" className="watch-more" aria-expanded={expanded}
        onClick={() => setExpanded(!expanded)}>{expanded ? 'Mostrar las primeras 3' : `Ver las ${signals.length} alertas`}</button>}
      <details className="mission-table-expand watch-method">
        <summary>Cómo se eligen las alertas</summary>
        <p>Agua. El promedio de los últimos cinco años analizados está al menos {data.rules.waterThreshold} % por debajo de la referencia.
          A partir de {data.rules.waterPriority} % se marca como prioridad alta. Esta prioridad sirve para revisar el caso y no estima cuándo podría secarse un lago.</p>
        <p>Vegetación. La pérdida de bosque del último año disponible supera en al menos {data.rules.vegetationPercent} % la mediana de los {data.rules.vegetationYears} años anteriores en la subcuenca local.</p>
        <p>Incendios. Se muestran las alertas del reporte FIRMS guardado. Las ejecuciones de prueba se identifican como simulacros.</p>
      </details>
    </>}
  </section>;
}
