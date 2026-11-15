'use client';

import { useId, useMemo, useState } from 'react';
import { X } from 'lucide-react';
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { displayDate, number, signed } from './data';
import { levels, severity, type Analysis, type RegionalTrend } from './regional-vegetation-data';
import { DataTable } from './ui';

const intervalMs = 10 * 24 * 60 * 60 * 1000;
const valueLabel = (value: number | null, unit = '') => value == null ? '—' : `${number(value, 4)}${unit ? ' ' + unit : ''}`;
const pct = (value: number | null) => value == null ? '—' : `${signed(value, 1)} %`;
const direction: Record<string, string> = { increasing: 'creciente', decreasing: 'decreciente', 'no trend': 'sin tendencia significativa', no_data: 'sin datos' };

function RegionalChart({ title, color, series }: { title: string; color: string; series: RegionalTrend }) {
  const [mode, setMode] = useState('series');
  const id = useId();
  const points = useMemo(() => {
    const data = series.series.map(({ date, value }) => ({ date, value, time: Date.parse(date) }));
    if (!data.length) return data;
    const start = data[0].time;
    const meanX = data.reduce((sum, row) => sum + (row.time - start), 0) / data.length;
    const meanY = data.reduce((sum, row) => sum + row.value, 0) / data.length;
    return data.map((row) => ({ ...row, trend: series.slope == null ? null : meanY + series.slope * (row.time - start - meanX) / intervalMs }));
  }, [series]);
  const domainUnit = mode === 'anomaly' ? '%' : series.unit === 'NDVI' ? '' : 'mm';
  const rows = mode === 'series' ? points : mode === 'anomaly'
    ? series.anomaly_series.map(({ date, value }) => ({ date, value: value - 100 }))
    : (series.climatology ?? []).map(({ dekad, lta }) => ({ date: String(dekad), value: lta }));
  const formatTick = (value: string) => mode === 'climate' ? value : value.slice(0, 4);
  return <section className="environment-panel regional-chart">
    <div className="mission-chart-heading">
      <div><h3>{title}</h3><p>{direction[series.trend] ?? series.trend} · {number(series.n_obs)} observaciones</p></div>
      <label htmlFor={id}><span id={id + '-label'}>Datos del gráfico de {title.toLowerCase()}</span>
        <select id={id} aria-labelledby={id + '-label'} value={mode} onChange={(event) => setMode(event.target.value)}>
          <option value="series">Serie y tendencia de Sen</option>
          <option value="anomaly" disabled={!series.anomaly_series.length}>Diferencia frente a lo habitual</option>
          <option value="climate" disabled={!series.climatology?.length}>Climatología (36 periodos)</option>
        </select></label>
    </div>
    {rows.length ? <div className="environment-chart">
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        <LineChart data={rows} margin={{ top: 13, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#2c4669" vertical={false} />
          <XAxis stroke="#b7c7e2" dataKey="date" minTickGap={38} tickFormatter={formatTick} />
          <YAxis stroke="#b7c7e2" domain={['auto', 'auto']} tickFormatter={(value) => number(value, 2)} width={65} unit={domainUnit ? ` ${domainUnit}` : ''} />
          <Tooltip contentStyle={{ background: '#101d38', borderColor: '#4d6b90', borderRadius: 12 }}
            labelFormatter={(value) => mode === 'climate' ? `Periodo ${value}` : displayDate(String(value))}
            formatter={(value) => typeof value === 'number' ? valueLabel(value, domainUnit) : '—'} />
          <Legend />
          <Line dataKey="value" type="linear" name={mode === 'series' ? 'Valor observado' : mode === 'anomaly' ? 'Anomalía (%)' : 'Promedio climático'}
            stroke={color} strokeWidth={2} dot={false} isAnimationActive={false} />
          {mode === 'series' && series.slope != null && <Line dataKey="trend" type="linear" name="Tendencia de Sen" stroke="#d2d9fb"
            strokeDasharray="5 4" strokeWidth={2} dot={false} isAnimationActive={false} />}
        </LineChart>
      </ResponsiveContainer>
    </div> : <p className="notice">El archivo no tiene valores en esta vista.</p>}
  </section>;
}

export function RegionalDetails({ detail, close }: { detail: Analysis; close: () => void }) {
  const { correlation, rainfall, ndvi, worst_period: worst } = detail;
  const [showTable, setShowTable] = useState(false);
  const valuesByDate = useMemo(() => new Map(ndvi.series.map(({ date, value }) => [date, value])), [ndvi.series]);
  return <section className="regional-details" id="diagnostico-provincial" tabIndex={-1} aria-labelledby="regional-case-title">
    <div className="panel regional-verdict">
      <div><p className="mission-eyebrow">{detail.adm1_name}</p><h3 id="regional-case-title">{detail.name}</h3>
        <p className="regional-verdict-tag" style={{ color: `rgb(${levels[detail.level].color.join(',')})` }}>{detail.verdict}</p>
        <p>{detail.explanation}</p></div>
      <button type="button" aria-label="Cerrar diagnóstico provincial" onClick={close}><X size={18} aria-hidden="true" /></button>
    </div>
    <p className="regional-period">{displayDate(detail.period.start)} – {displayDate(detail.period.end)} · {number(detail.n_pixels)} píxeles de referencia</p>
    <div className="regional-metrics">
      {[
        ['Valor p de lluvia', valueLabel(rainfall.p_value)], ['Valor p de NDVI', valueLabel(ndvi.p_value)],
        ['Pendiente de Sen (lluvia)', valueLabel(rainfall.slope, 'mm por periodo')],
        ['Pendiente de Sen (NDVI)', valueLabel(ndvi.slope, 'por periodo')],
        ['Correlación r', valueLabel(correlation.r)],
        ['Retraso de la vegetación', correlation.lag_dekads == null ? '—' : `${correlation.lag_dekads} periodos · aprox. ${correlation.lag_dekads * 10} días`],
      ].map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}
    </div>
    <p className="muted">La correlación compara lluvia y vegetación. El valor p indica qué tan compatible es la señal con la ausencia de tendencia. Cada periodo dura aproximadamente 10 días.</p>
    {!!detail.windows.length && <section className="panel regional-windows">
      <h3>Diagnóstico por periodo</h3>
      <p className="muted">El índice combina la diferencia de lluvia (60 %) y de NDVI (40 %) frente a la referencia original.</p>
      <div className="regional-window-grid">{detail.windows.map((window) => <article key={window.label} title={window.evidence}>
        <h4>{window.label}</h4><strong style={{ color: `rgb(${severity[window.compound_severity].color.join(',')})` }}>{severity[window.compound_severity].label}</strong>
        <p>Lluvia {pct(window.rainfall_anomaly_pct)}<br />NDVI {pct(window.ndvi_anomaly_pct)}</p>
      </article>)}</div>
      {worst && <div className="regional-worst"><h4>Periodo con mayor déficit · {severity[worst.compound_severity].label}</h4>
        <p>{displayDate(worst.start)} – {displayDate(worst.end)} · Lluvia {pct(worst.rainfall_anomaly_pct)} · NDVI {pct(worst.ndvi_anomaly_pct)}</p></div>}
    </section>}
    <div className="regional-charts">
      <RegionalChart title="Lluvia acumulada" color="#87baff" series={rainfall} />
      <RegionalChart title="Verdor de la vegetación (NDVI)" color="#9be8a6" series={ndvi} />
    </div>
    <details className="mission-table-expand panel fire-report-details" onToggle={(event) => setShowTable(event.currentTarget.open)}>
      <summary>Ver observaciones por fecha</summary>
      {showTable && <DataTable rows={rainfall.series.map(({ date, value }) => ({
        Fecha: date, 'Lluvia (mm)': valueLabel(value), NDVI: valueLabel(valuesByDate.get(date) ?? null),
      }))} />}
    </details>
  </section>;
}
