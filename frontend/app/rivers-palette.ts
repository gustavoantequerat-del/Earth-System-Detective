import type { OsmKind } from './data';

type Tone = { rgb: [number, number, number]; css: string; label: string };
const tone = (rgb: [number, number, number], label: string): Tone => ({ rgb, css: `rgb(${rgb.join(',')})`, label });

/** Color del tramo según cuánto cambió el agua en el cauce (últimos 5 años contra 1985-2000). */
export function waterTone(pct: number | null): Tone {
  if (pct == null) return tone([148, 163, 168], 'Sin dato comparable');
  if (pct <= -40) return tone([244, 112, 103], 'Pérdida fuerte (40 % o más)');
  if (pct <= -15) return tone([247, 184, 75], 'Pérdida moderada (15 a 40 %)');
  return tone([86, 196, 245], 'Estable o con más agua');
}
export const waterLegend = [waterTone(-50), waterTone(-20), waterTone(0)];

export const kindColors: Record<OsmKind, Tone> = {
  'Canal o acequia': tone([45, 212, 191], 'Canal o acequia'),
  'Represa o toma': tone([129, 140, 248], 'Represa o toma'),
  Reservorio: tone([96, 165, 250], 'Reservorio'),
  'Mina o cantera': tone([244, 112, 103], 'Mina o cantera'),
  'Planta de tratamiento': tone([163, 230, 53], 'Planta de tratamiento'),
  'Piletas de sal': tone([250, 204, 21], 'Piletas de sal'),
};

export const kindInfo: Record<OsmKind, string> = {
  'Canal o acequia': 'Cauces artificiales que llevan agua del río a cultivos o la sacan de la ciudad (desagües). Indican posible extracción.',
  'Represa o toma': 'Obras que retienen o desvían agua del río. Son el punto donde el agua sale del cauce.',
  Reservorio: 'Estanques o embalses que almacenan agua, por ejemplo para riego o ganado.',
  'Mina o cantera': 'Explotaciones mineras: usan agua y pueden contaminarla, aunque su volumen es difícil de medir desde el satélite.',
  'Planta de tratamiento': 'Plantas de tratamiento de aguas servidas. Su ausencia o mal funcionamiento afecta la calidad del agua.',
  'Piletas de sal': 'Piletas para producir sal por evaporación.',
};

export const escapeHtml = (value: string) => value.replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);
