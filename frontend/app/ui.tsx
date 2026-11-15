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

export function DataTable({ rows, empty = 'Sin registros.' }: { rows: Row[]; empty?: string }) {
  if (!rows.length) return <p className="muted">{empty}</p>;
  const columns = Object.keys(rows[0]);
  return <div className="table-wrap"><table>
    <thead><tr>{columns.map((column) => <th key={column} scope="col">{column.replaceAll('_', ' ')}</th>)}</tr></thead>
    <tbody>{rows.map((row, index) => <tr key={index}>{columns.map((column) => <td key={column}>{row[column] ?? '—'}</td>)}</tr>)}</tbody>
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
