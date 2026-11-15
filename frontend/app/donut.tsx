'use client';

import { useState, type ReactNode } from 'react';
import { number } from './data';

export interface Slice { key: string; label: string; value: number; color: string; note?: string }

/** Gráfico de torta (dona) accesible: se resalta una porción al pasar el mouse o enfocar su fila de la leyenda. */
export function Donut({ slices, unit = '', center, centerLabel, size = 190, digits = 0, label }: {
  slices: Slice[]; unit?: string; center?: ReactNode; centerLabel?: string; size?: number; digits?: number; label: string;
}) {
  const [active, setActive] = useState<string | null>(null);
  const shown = slices.filter((slice) => slice.value > 0);
  const total = shown.reduce((sum, slice) => sum + slice.value, 0);
  let start = 0;
  const gradient = shown.map((slice) => {
    const end = start + slice.value / (total || 1) * 100;
    const dim = active && active !== slice.key ? '55' : '';
    const segment = `${slice.color}${dim} ${start}% ${end}%`;
    start = end;
    return segment;
  }).join(', ');
  const highlighted = shown.find((slice) => slice.key === active);
  const fmt = (value: number) => `${number(value, digits)}${unit ? ` ${unit}` : ''}`;
  return <div className="donut-block">
    <div className="donut" role="img" aria-label={`${label}: ${shown.map((slice) => `${slice.label} ${fmt(slice.value)}`).join('; ')}`}
      style={{ width: size, height: size, background: total ? `conic-gradient(${gradient})` : 'var(--field)' }}>
      <div>
        <b>{highlighted ? `${number(highlighted.value / total * 100)} %` : center ?? fmt(total)}</b>
        <span>{highlighted ? highlighted.label : centerLabel ?? 'total'}</span>
      </div>
    </div>
    <ul className="donut-legend">
      {shown.map((slice) => <li key={slice.key}>
        <button type="button" className={active === slice.key ? 'selected' : undefined}
          onPointerEnter={() => setActive(slice.key)} onPointerLeave={() => setActive(null)}
          onFocus={() => setActive(slice.key)} onBlur={() => setActive(null)}>
          <i style={{ background: slice.color }} aria-hidden="true" />
          <span>{slice.label}{slice.note && <small>{slice.note}</small>}</span>
          <b>{fmt(slice.value)}</b>
        </button>
      </li>)}
    </ul>
  </div>;
}

/** Barra horizontal que crece desde el centro: negativo a la izquierda, positivo a la derecha. */
export function DivergingBars({ rows, unit = '%', max }: {
  rows: { key: string; label: string; value: number | null; hint?: string; color?: string }[]; unit?: string; max?: number;
}) {
  const scale = max ?? Math.max(1, ...rows.map((row) => Math.abs(row.value ?? 0)));
  return <ul className="diverging">
    {rows.map((row) => {
      const value = row.value;
      const width = value == null ? 0 : Math.min(50, Math.abs(value) / scale * 50);
      const negative = (value ?? 0) < 0;
      return <li key={row.key}>
        <span className="diverging-label">{row.label}{row.hint && <small>{row.hint}</small>}</span>
        <span className="diverging-track" aria-hidden="true">
          <i className={negative ? 'neg' : 'pos'} style={{ width: `${width}%`, [negative ? 'right' : 'left']: '50%',
            ...(row.color ? { background: row.color } : {}) }} />
        </span>
        <b className={value == null ? 'na' : negative ? 'neg' : 'pos'}>{value == null ? 's/d' : `${value > 0 ? '+' : ''}${number(value)} ${unit}`}</b>
      </li>;
    })}
  </ul>;
}
