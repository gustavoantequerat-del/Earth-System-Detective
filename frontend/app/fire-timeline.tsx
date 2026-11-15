'use client';

import { Pause, Play, SkipBack, SkipForward } from 'lucide-react';
import { number } from './data';

export interface FireFrame {
  key: string;
  label: string;
  total?: number;
}

export function FireTimeline({ frames, index, playing, speed, height, select, toggle, setSpeed, setHeight, flat, comparison, maximum, unit }: {
  frames: FireFrame[];
  index: number;
  playing: boolean;
  speed: number;
  height: number;
  select: (index: number) => void;
  toggle: () => void;
  setSpeed: (speed: number) => void;
  setHeight: (height: number) => void;
  flat: boolean;
  comparison: boolean;
  maximum: number;
  unit: string;
}) {
  const frame = frames[index];
  const last = Math.max(0, frames.length - 1);
  const peak = Math.max(1, ...frames.map((frame) => frame.total ?? 0));
  const path = frames.map(({ total }, position) => `${position === 0 ? 'M' : 'L'}${(position / Math.max(last, 1) * 420).toFixed(1)},${(78 - (total ?? 0) / peak * 68).toFixed(1)}`).join('');
  return <aside className="fire-timeline" aria-label="Controles de la animación">
    <div className="fire-timeline-current">
      <p className="mission-eyebrow">Periodo en el mapa</p>
      <strong id="fire-replay-period">{frame?.label}</strong>
      {frame?.total != null && <p>{number(frame.total, 1)} focos representados</p>}
    </div>
    {last > 0 && <>
      <label htmlFor="fire-play-frame">Línea de tiempo</label>
      <input id="fire-play-frame" type="range" min={0} max={last} step={1} value={index} aria-valuetext={frame?.label}
        onChange={(event) => select(Number(event.target.value))} />
      <div className="fire-timeline-actions">
        <button type="button" aria-label="Periodo anterior" disabled={index === 0} onClick={() => select(index - 1)}><SkipBack size={16} aria-hidden="true" /></button>
        <button type="button" id="fire-play-toggle" className="fire-play" onClick={toggle}>{playing ? <Pause size={18} aria-hidden="true" /> : <Play size={18} aria-hidden="true" />}
          {playing ? 'Pausar' : 'Reproducir'}</button>
        <button type="button" aria-label="Periodo siguiente" disabled={index === last} onClick={() => select(index + 1)}><SkipForward size={16} aria-hidden="true" /></button>
      </div>
      <label htmlFor="fire-play-speed">Velocidad
        <select id="fire-play-speed" value={speed} onChange={(event) => setSpeed(Number(event.target.value))}>
          <option value={1100}>Lenta</option><option value={650}>Normal</option><option value={330}>Rápida</option>
        </select></label>
    </>}
    {last > 0 && frames.some((entry) => entry.total != null) && <div className="fire-spark">
      <p>Evolución de los focos</p><small>Toca un punto de la gráfica para ir a ese periodo.</small>
      <svg aria-hidden="true" focusable="false" viewBox="0 0 420 83" preserveAspectRatio="none"
        onPointerDown={(event) => {
          const bounds = event.currentTarget.getBoundingClientRect();
          select(Math.round(Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width)) * last));
        }}>
        <path d={path} /><line x1={index / last * 420} x2={index / last * 420} y1={0} y2={83} />
      </svg>
      <div className="fire-scale-ticks"><span>{frames[0].key.slice(0, 4)}</span><span>{frames[last].key.slice(0, 4)}</span></div>
    </div>}
    {!flat && <label htmlFor="fire-height">Altura visual de las barras <output htmlFor="fire-height">{number(height, 1)}×</output>
      <input id="fire-height" type="range" min={.5} max={2.5} step={.1} value={height}
        aria-valuetext={`${number(height, 1)} veces la altura normal`} onChange={(event) => setHeight(Number(event.target.value))} /></label>}
    <div className="fire-timeline-legend">
      <p>Escala de color</p><div className={comparison ? 'fire-gradient divergent' : 'fire-gradient'} />
      <div className="fire-scale-ticks"><span>{comparison ? `−${number(maximum)}` : '0'}</span>
        <span>{comparison ? '0' : number(maximum / 2, 1)}</span><span>≥ {number(maximum)} {unit}</span></div>
      <small>{comparison ? 'Azul indica menos; naranja indica más que la referencia.' : 'Barras más oscuras señalan más focos. La escala se mantiene al cambiar la fecha.'}</small>
    </div>
  </aside>;
}
