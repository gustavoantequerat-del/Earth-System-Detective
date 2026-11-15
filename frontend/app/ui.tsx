import { useId, type CSSProperties, type ReactNode } from 'react';
import { Activity, CircleHelp, CloudSunRain, Footprints, Info, ShieldCheck, Siren, Waves } from 'lucide-react';
import { states, type Row, type State } from './data';

const icons = {
  'Huella humana': Footprints, 'Alerta temprana': Siren, 'Aguas arriba': Waves, Incalculable: CircleHelp, 'Sin explicar': CircleHelp,
  'Causa climatica': CloudSunRain, Intacto: ShieldCheck, 'Evidencia insuficiente': CircleHelp,
  'Evidencia reforzada de intervencion': ShieldCheck, 'Indicios de intervencion humana': Footprints,
  'Perdida no explicada': Activity, 'Sin perdida anomala detectada': Activity,
};

export function Status({ state }: { state: State }) {
  const config = states[state];
  const Icon = icons[state];
  return <span className="status" style={{ '--status': `rgb(${config.rgb.join(',')})` } as CSSProperties}>
    <Icon size={15} aria-hidden="true" /> {config.label}
  </span>;
}

const skipBars = /(año|ano|year|semana|fecha|date|^id$|_id|lat|lon|run|hora|mes$|month|versi)/i;
const parseNumber = (value: unknown) => {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value !== 'string') return null;
  const text = value.trim().replace(/\s*(%|ha|mm|°C|focos?)$/i, '');
  if (!/^[-−+]?\d{1,3}(\.\d{3})*(,\d+)?$|^[-−+]?\d+([.,]\d+)?$/.test(text)) return null;
  const normal = text.replace('−', '-');
  return Number(/,\d+$/.test(normal) || /\.\d{3}(\.|$)/.test(normal) ? normal.replaceAll('.', '').replace(',', '.') : normal);
};
const levelOf = (text: string) => /^(alta|fuerte|buena|elegible)$/i.test(text) ? 'high'
  : /^(media|moderada)$/i.test(text) ? 'mid' : /^(baja|d[eé]bil|poca calidad|insuficiente)$/i.test(text) ? 'low' : null;
const stateByLabel = new Map(Object.entries(states).flatMap(([key, value]) => [[key, key], [value.label, key]])) as Map<string, State>;

/** Tabla con lectura gráfica: barras en columnas numéricas, insignias para Sí/No y chips para los diagnósticos. */
export function DataTable({ rows, empty = 'Sin registros.' }: { rows: Row[]; empty?: string }) {
  if (!rows.length) return <p className="muted">{empty}</p>;
  const columns = Object.keys(rows[0]);
  const scales = new Map<string, number>();
  for (const column of columns) {
    if (skipBars.test(column)) continue;
    const values = rows.map((row) => row[column]).filter((value) => value != null && value !== '');
    const numbers = values.map(parseNumber).filter((value): value is number => value != null);
    const yearLike = numbers.every((value) => Number.isInteger(value) && value >= 1900 && value <= 2100);
    if (numbers.length >= 2 && numbers.length >= values.length * .6 && !yearLike && new Set(numbers).size > 1) {
      scales.set(column, Math.max(...numbers.map(Math.abs)) || 1);
    }
  }
  const cell = (column: string, value: Row[string]) => {
    if (value == null || value === '') return <span className="cell-empty">—</span>;
    const text = String(value);
    if (/^(sí|si|true)$/i.test(text)) return <span className="cell-badge yes">Sí</span>;
    if (/^(no|false)$/i.test(text)) return <span className="cell-badge no">No</span>;
    const level = /evidencia|calidad|confianza|nivel/i.test(column) ? levelOf(text) : null;
    if (level) return <span className={`cell-level ${level}`}>{text}</span>;
    const state = stateByLabel.get(text);
    if (state && /estado|diagn|veredicto|state/i.test(column)) return <Status state={state} />;
    const scale = scales.get(column);
    const amount = scale ? parseNumber(value) : null;
    if (scale && amount != null) {
      return <span className="cell-bar"><span>{text}</span>
        <i aria-hidden="true" className={amount < 0 ? 'neg' : undefined} style={{ width: `${Math.max(2, Math.abs(amount) / scale * 100)}%` }} /></span>;
    }
    return text;
  };
  return <div className="table-wrap"><table className="data-table">
    <thead><tr>{columns.map((column) => <th key={column} scope="col" className={scales.has(column) ? 'num' : undefined}>{column.replaceAll('_', ' ')}</th>)}</tr></thead>
    <tbody>{rows.map((row, index) => <tr key={index}>{columns.map((column) =>
      <td key={column} className={scales.has(column) ? 'num' : undefined}>{cell(column, row[column])}</td>)}</tr>)}</tbody>
  </table></div>;
}

/** Icono "i" con una explicación que aparece al pasar el mouse, al enfocar con teclado o al tocar. */
export function InfoTip({ label, children, align = 'center' }: { label: string; children: ReactNode; align?: 'center' | 'start' | 'end' }) {
  const id = useId();
  return <span className={`info-tip info-${align}`}>
    <button type="button" className="info-tip-button" aria-label={`Qué significa: ${label}`} aria-describedby={id}>
      <Info size={14} aria-hidden="true" />
    </button>
    <span role="tooltip" id={id} className="info-tip-bubble"><strong>{label}</strong>{children}</span>
  </span>;
}
