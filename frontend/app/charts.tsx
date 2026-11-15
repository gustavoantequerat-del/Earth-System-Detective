'use client';

import { useState } from 'react';
import {
  Area as ChartArea, Bar, BarChart, CartesianGrid, Cell, ComposedChart, Legend, Line,
  ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { areaNames, number, type Area, type BodyDetail, type WaterBody } from './data';

const axis = { fill: '#9daeb4', fontSize: 12 };
const tooltip = { background: '#14242c', borderColor: '#36515c', color: '#edf4f4', borderRadius: 8 };
const causes: Record<string, { label: string; color: string }> = {
  'Sequia y calor': { label: 'Sequía y calor', color: '#ff9734' },
  'Lluvia menos evaporacion': { label: 'Lluvia menos evaporación', color: '#ffa26b' },
  'El Nino': { label: 'El Niño', color: '#ffd647' },
  'Huella humana': { label: 'Huella humana', color: '#ff3d66' },
  'Sin explicar': { label: 'Sin explicar', color: '#9daeb4' },
  Incalculable: { label: 'Incalculable', color: '#a5b4fc' },
  'Cambio esperado por modelo': { label: 'Cambio esperado por modelo', color: '#86a9ff' },
  'Diferencia de tendencias no atribuida': { label: 'Diferencia no atribuida', color: '#a5b4fc' },
};
const axisNumber = (value: number) => new Intl.NumberFormat('es-BO', { notation: 'compact', maximumFractionDigits: 1 }).format(value);

export function ClimateCharts({ body }: { body: WaterBody }) {
  const hasBand = Boolean(body.expected_lower && body.expected_upper && body.interval_level);
  const reference = body.method_version || body.climate_reliable === false ? 'Referencia modelada' : 'Esperada por el clima';
  const series = body.years.map((year, index) => {
    const low = body.expected_lower?.[index];
    const high = body.expected_upper?.[index];
    return { year, observed: body.observed[index], expected: body.expected[index], oni: body.oni[index],
      interval: low == null || high == null ? null : [low, high] };
  });
  const breakdown = Object.entries(body.decomposition_ha).map(([key, ha]) => ({
    cause: causes[key]?.label ?? key, color: causes[key]?.color ?? '#9daeb4', ha,
  }));
  return <div className="chart-grid">
    <figure>
      <h3>Agua observada y {reference.toLowerCase()}</h3>
      <div className="chart"><ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <ComposedChart data={series} margin={{ top: 8, right: 12, left: 6, bottom: 4 }}>
          <CartesianGrid stroke="#26383f" vertical={false} />
          <XAxis type="number" dataKey="year" domain={['dataMin', 'dataMax']} tick={axis} tickFormatter={(value) => String(value)} />
          <YAxis tick={axis} tickFormatter={axisNumber} width={49} />
          {series.filter(({ oni }) => oni >= 0.5).map(({ year }) => (
            <ReferenceArea key={year} x1={year} x2={Math.min(year + 1, body.years.at(-1) ?? year)} fill="#ff9734" fillOpacity={0.16} />
          ))}
          <ReferenceLine x={body.baseline_end} stroke="#d6e1e5" strokeDasharray="3 3" />
          <Tooltip contentStyle={tooltip} formatter={(value) => Array.isArray(value)
            ? `${number(Number(value[0]))} – ${number(Number(value[1]))} ha` : `${number(Number(value))} ha`} />
          <Legend />
          {hasBand && <ChartArea dataKey="interval" name="Banda aproximada" stroke="none" fill="#77a4ff" fillOpacity={0.26} />}
          <Line dataKey="observed" name="Observada" type="linear" stroke="#cedfe4" strokeWidth={2} dot={false} />
          <Line dataKey="expected" name={reference} type="linear" stroke="#5e9dff" strokeWidth={2} strokeDasharray="6 4" dot={false} />
        </ComposedChart>
      </ResponsiveContainer></div>
      <figcaption>Superficie en hectáreas. Franjas naranjas para El Niño. La línea vertical marca el fin del periodo base ({body.baseline_end}).</figcaption>
      {hasBand && <figcaption>Banda bootstrap aproximada del {number(100 * body.interval_level!)} %.
        {body.backtest?.coverage != null && ` Cobertura posterior: ${number(body.backtest.coverage * 100)} %.`}</figcaption>}
      {body.climate_reliable === false && <figcaption>El ajuste climático no superó los criterios del método. La referencia es el promedio del periodo base.</figcaption>}
    </figure>
    <figure>
      <h3>De dónde viene el cambio</h3>
      <div className="chart"><ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <BarChart data={breakdown} layout="vertical" margin={{ top: 8, right: 10, left: 0, bottom: 4 }}>
          <CartesianGrid stroke="#26383f" horizontal={false} />
          <XAxis type="number" tick={axis} tickFormatter={axisNumber} />
          <YAxis type="category" dataKey="cause" tick={axis} width={98} />
          <ReferenceLine x={0} stroke="#9daeb4" />
          <Tooltip contentStyle={tooltip} cursor={{ fill: '#26383f' }} formatter={(value) => `${number(Number(value))} ha`} />
          <Bar dataKey="ha" name="Cambio" barSize={23}>{breakdown.map(({ cause, color }) => <Cell key={cause} fill={color} />)}</Bar>
        </BarChart>
      </ResponsiveContainer></div>
      <figcaption>{body.method_version
        ? 'Cambio modelado y diferencia de tendencias en hectáreas a lo largo del periodo analizado.'
        : 'Hectáreas ganadas o perdidas entre el promedio del periodo base y el de los últimos cinco años.'}</figcaption>
    </figure>
  </div>;
}

export function CrossChecks({ detail }: { detail: BodyDetail }) {
  const { verification, river } = detail;
  if (!verification && !river) return null;
  const water = verification ? Object.entries(verification.agua_landsat ?? {}).map(([year, landsat]) => ({
    year: Number(year), landsat, mapbiomas: verification.agua_mapbiomas?.[year],
  })) : [];
  const channel = river ? Object.entries(river.agua_cauce_ha).map(([year, ha]) => ({ year: Number(year), ha })) : [];

  return <>
    {verification && <details className="proof-group">
      <summary>Verificación cruzada de las fuentes</summary>
      <p className="muted">Correlación Landsat–MapBiomas para superficie de agua: {verification.r_agua_landsat_mapbiomas == null
        ? 'Sin dato' : number(verification.r_agua_landsat_mapbiomas, 2)}. Correlación NASA POWER–CHIRPS para lluvia:
        {' '}{verification.r_lluvia_power_chirps == null ? 'Sin dato' : number(verification.r_lluvia_power_chirps, 2)}.</p>
      {!!water.length && <div className="chart"><ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <ComposedChart data={water}>
          <CartesianGrid stroke="#303e60" vertical={false} />
          <XAxis type="number" dataKey="year" domain={['dataMin', 'dataMax']} tick={axis} />
          <YAxis tick={axis} tickFormatter={axisNumber} width={56} /><Legend />
          <Tooltip contentStyle={tooltip} formatter={(value) => `${number(Number(value))} ha`} />
          <Line dataKey="landsat" name="Landsat" stroke="#cedfe4" dot={false} />
          <Line dataKey="mapbiomas" name="MapBiomas Agua" stroke="#5e9dff" dot={false} />
        </ComposedChart>
      </ResponsiveContainer></div>}
    </details>}
    {!!channel.length && <details className="proof-group">
      <summary>Agua en el cauce del Desaguadero</summary>
      <p className="muted">Superficie de agua observada por satélite en el río. El análisis carece de estaciones de caudal.</p>
      <div className="chart"><ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <ComposedChart data={channel}>
          <CartesianGrid stroke="#303e60" vertical={false} />
          <XAxis type="number" dataKey="year" domain={['dataMin', 'dataMax']} tick={axis} />
          <YAxis tick={axis} tickFormatter={axisNumber} width={56} />
          <Tooltip contentStyle={tooltip} formatter={(value) => `${number(Number(value))} ha`} />
          <Line dataKey="ha" name="Agua en el cauce" stroke="#5eead4" dot={false} />
        </ComposedChart>
      </ResponsiveContainer></div>
    </details>}
  </>;
}

export function WaterCharts({ detail }: { detail: BodyDetail }) {
  const areas = (Object.keys(areaNames) as Area[]).filter((area) => detail.water.some((row) => row.area === area));
  const [area, setArea] = useState(areas[0]);
  if (!area) return <p className="muted">Sin series de agua artificial para este cuerpo de agua.</p>;
  const { result } = detail;
  const byYear = new Map<number, Record<string, number | null>>();
  result.years.forEach((year, index) => byYear.set(year, { year, lake: result.observed[index] }));
  for (const row of detail.water) {
    if (row.area !== area) continue;
    const year = byYear.get(row.year) ?? { year: row.year };
    year[row.suspect] = row.value;
    byYear.set(row.year, year);
  }
  const series = [...byYear].sort(([left], [right]) => left - right).map(([year, row]) => ({
    year, lake: row.lake, natural: row.natural_water_ha,
    artificial: row.artificial_water_ha == null && row.mining_water_ha == null ? null :
      (row.artificial_water_ha ?? 0) + (row.mining_water_ha ?? 0),
  }));
  function average(start: number, end: number) {
    const items = series.filter((item) => item.year >= start && item.year <= end).flatMap((item) =>
      item.artificial == null ? [] : [item.artificial]);
    return items.length ? `${number(items.reduce((sum, value) => sum + value, 0) / items.length)} ha` : 'Sin datos';
  }
  return <figure>
    <div className="segmented">{areas.map((option) => <button type="button" key={option}
      aria-pressed={option === area} onClick={() => setArea(option)}>{areaNames[option]}</button>)}</div>
    <div className="chart"><ResponsiveContainer width="100%" height="100%" minWidth={0}>
      <ComposedChart data={series} margin={{ top: 8, right: 10, left: 6, bottom: 4 }}>
        <CartesianGrid stroke="#26383f" vertical={false} />
        <XAxis dataKey="year" type="number" domain={['dataMin', 'dataMax']} tick={axis} tickFormatter={(value) => String(value)} />
        <YAxis yAxisId="natural" tick={axis} tickFormatter={axisNumber} width={54} />
        <YAxis yAxisId="artificial" orientation="right" tick={{ ...axis, fill: '#32daeb' }} tickFormatter={axisNumber} width={54} />
        <Tooltip contentStyle={tooltip} formatter={(value) => `${number(Number(value))} ha`} />
        <Legend />
        <ChartArea yAxisId="artificial" dataKey="artificial" name="Agua artificial" stroke="#32daeb" fill="#32daeb" fillOpacity={0.2} />
        <Line yAxisId="natural" dataKey="lake" name="Esta laguna (Landsat)" stroke="#9cbaff" strokeWidth={2} dot={false} />
        <Line yAxisId="natural" dataKey="natural" name="Agua natural del área" stroke="#4f7cff" strokeWidth={2} dot={false} />
      </ComposedChart>
    </ResponsiveContainer></div>
    <figcaption>Agua artificial promedio, {average(1985, 1990)} (1985–1990) y {average(2020, 2024)} (2020–2024).
      El eje derecho incluye represas, estanques y pozas mineras de MapBiomas Agua.</figcaption>
  </figure>;
}
