export const states = {
  'Huella humana': { label: 'Huella humana', rgb: [255, 122, 122], action: 'Prevenir. Controlar la actividad sospechosa, proteger la cuenca y restaurar.' },
  'Alerta temprana': { label: 'Alerta temprana', rgb: [196, 161, 255], action: 'Actuar temprano para proteger la cuenca.' },
  Incalculable: { label: 'Incalculable', rgb: [255, 209, 102], action: 'Revisar qué datos o pruebas faltan para calcular la causa de la pérdida.' },
  'Sin explicar': { label: 'Sin explicar', rgb: [255, 209, 102], action: 'Revisar qué datos o pruebas faltan para calcular la causa de la pérdida.' },
  'Causa climatica': { label: 'Causa climática', rgb: [255, 162, 107], action: 'Adaptarse con cosecha de agua, reservorios y planes de sequía.' },
  Intacto: { label: 'Intacto', rgb: [94, 230, 168], action: 'Mantener el seguimiento.' },
  'Evidencia reforzada de intervencion': { label: 'Evidencia reforzada de intervención', rgb: [255, 122, 122], action: 'Revisar la intervención documentada y sus supuestos.' },
  'Indicios de intervencion humana': { label: 'Indicios de intervención humana', rgb: [255, 162, 107], action: 'Revisar las señales y buscar evidencia independiente de la actividad.' },
  'Perdida no explicada': { label: 'Pérdida no explicada', rgb: [255, 209, 102], action: 'Investigar la hidrología, la calidad de los datos y las actividades en la cuenca.' },
  'Evidencia insuficiente': { label: 'Evidencia insuficiente', rgb: [189, 195, 211], action: 'Revisar la calidad, el periodo base y la validación antes de interpretar causas.' },
  'Sin perdida anomala detectada': { label: 'Sin pérdida anómala detectada', rgb: [112, 199, 255], action: 'Mantener el seguimiento de la superficie observada y de la presión en la cuenca.' },
} as const;

export type State = keyof typeof states;
export const diagnosisMeaning: Record<State, string> = {
  'Huella humana': 'El análisis encontró señales de actividad humana compatibles con la pérdida de agua. El diagnóstico necesita contrastarse con evidencia de campo.',
  'Alerta temprana': 'Se detectaron cambios o presiones que vale la pena seguir antes de que la pérdida de agua sea mayor.',
  Incalculable: 'Hay señales de pérdida, pero los datos disponibles no permiten estimar con confianza qué la explica.',
  'Sin explicar': 'El agua disminuyó y las pruebas disponibles aún no permiten identificar la causa.',
  'Causa climatica': 'La pérdida de agua observada es coherente con las variaciones del clima incluidas en el análisis.',
  Intacto: 'El método no detectó una pérdida anormal de agua en el periodo analizado.',
  'Evidencia reforzada de intervencion': 'Varias pruebas y registros independientes respaldan una posible intervención humana.',
  'Indicios de intervencion humana': 'Coinciden algunas señales de actividad humana y cambios en el agua. Se necesita evidencia adicional para confirmar su relación.',
  'Perdida no explicada': 'Se encontró una pérdida mayor que la esperada y la evidencia disponible aún no permite atribuirla.',
  'Evidencia insuficiente': 'La calidad o cantidad de datos limita lo que el modelo puede concluir.',
  'Sin perdida anomala detectada': 'La superficie observada se mantuvo dentro de los cambios esperados por el modelo.',
};

export const searchKey = (value: string) => value.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLocaleLowerCase('es').trim();
export type Method = 'balance' | 'conservative';
export const methodNames: Record<Method, string> = { balance: 'Balance hídrico', conservative: 'Modelo conservador' };
export const methodStates: Record<Method, State[]> = {
  balance: ['Huella humana', 'Alerta temprana', 'Incalculable', 'Causa climatica', 'Intacto'],
  conservative: ['Evidencia reforzada de intervencion', 'Indicios de intervencion humana', 'Perdida no explicada',
    'Evidencia insuficiente', 'Sin perdida anomala detectada'],
};
export const humanEvidenceStates: State[] = ['Huella humana', 'Evidencia reforzada de intervencion', 'Indicios de intervencion humana'];
export type Area = 'subcuenca_local' | 'cuenca_aporte';
export const areaNames: Record<Area, string> = { subcuenca_local: 'Cerca de la laguna', cuenca_aporte: 'Toda la cuenca de aporte' };
export const reviewOutcomes = {
  'En revision': 'En revisión',
  'Confirmado en campo': 'Confirmado en campo',
  'Falso positivo': 'Falso positivo',
  'Requiere mas datos': 'Requiere más datos',
};

export interface Suspect {
  suspect: string;
  label: string;
  evidence: string;
  onset: number | null;
  precedes: boolean;
  r2: number | null;
  indirect?: boolean;
  eligible?: boolean;
  data_provenance?: string;
  p_adjusted?: number | null;
  relation_beyond_trend?: boolean;
  together_with?: string[];
}

export interface WaterBody {
  body_id: string;
  name: string;
  lat: number;
  lon: number;
  control_id?: string;
  department?: string;
  state: State;
  confidence: string;
  years: number[];
  observed: (number | null)[];
  expected: (number | null)[];
  expected_lower?: (number | null)[];
  expected_upper?: (number | null)[];
  interval_level?: number;
  oni: number[];
  baseline_end: number;
  baseline_mean_ha: number;
  climate_r2: number | null;
  climate_reliable?: boolean;
  climate_fit?: Record<string, number | null>;
  why?: string[];
  climate_share?: number | null;
  data_quality?: { level: string; r_jrc?: number | null; interpolated_years?: number[] };
  n_pass: number;
  trend: { change_pct: number; sen_ha_per_year: number; p: number; p_holm: number };
  tests: Record<string, { pass: boolean | null; evaluated?: boolean; detail: string }>;
  decomposition_ha: Record<string, number>;
  backtest?: { coverage?: number | null; mae_ha?: number | null; mae_pct?: number | null };
  method_version?: string;
  selected_model?: string;
  model_comparison?: {
    method: string; selected: boolean; cv_n: number; cv_mae_ha: number | null; mae_ha: number | null;
  }[];
  model_validation?: { reliable: boolean; base_n: number; cv_n: number; interval_method: string; climate_attribution_eligible: boolean };
  quality?: { eligible: boolean; base_observed_n: number; imputed_water_n: number; reasons: string[] };
  control_validation?: { eligible: boolean; reviewed?: boolean; reasons: string[] };
  independent_evidence?: { source: string; suspect: string; year: number }[];
  suspects: Suspect[];
  ha?: number;
}

export interface Place {
  name: string;
  detail: string;
  kind: string;
  dist_km: number;
  lat: number;
  lon: number;
  osm: string;
}

export interface BodyDetail {
  result: WaterBody;
  places: Place[];
  imageYears: { year: number; mask: boolean }[];
  context: { years: [number, number]; window_km: number; changes_ha: Record<string, number>;
    legend: Record<string, { label: string; color: string }> } | null;
  water: { area: Area; year: number; suspect: string; value: number }[];
  vegetation?: { area: Area; year: number; suspect: string; value: number }[];
  climate?: ClimateYear[];
  catchment?: { areaKm2: number | null; subbasins: number | null; upstream: string[] } | null;
  verification: {
    r_agua_landsat_mapbiomas: number | null; r_lluvia_power_chirps: number | null;
    lluvia_media_power_mm: number | null; lluvia_media_chirps_mm: number | null;
    agua_landsat: Record<string, number | null>; agua_mapbiomas: Record<string, number | null>;
  } | null;
  river: { agua_cauce_ha: Record<string, number>; deficit_pct: Record<string, number> } | null;
}

export interface ClimateYear {
  year: number;
  waterHa: number | null;
  jrcHa: number | null;
  missingPct: number | null;
  powerMm: number | null;
  chirpsMm: number | null;
  rainMm: number | null;
  tempC: number | null;
  petMm: number | null;
  storageCm: number | null;
  oni: number | null;
}

export interface WatchSignal {
  id: string;
  name: string;
  type: 'agua' | 'vegetacion' | 'incendios';
  level: 'prioridad' | 'seguimiento';
  metric: number;
  reference: number | null;
  from: string;
  to: string;
  source: string;
  state?: State;
  area?: string;
}

export interface WatchlistData {
  signals: WatchSignal[];
  sample: boolean;
  weekly: { date: string; drill: boolean } | null;
  rules: { waterThreshold: number; waterPriority: number; vegetationPercent: number; vegetationYears: number };
}

export interface Snapshot {
  results: WaterBody[];
  national: WaterBody[];
  artificial: { year: number; points: { tipo: string; ha: number; lat: number; lon: number }[] } | null;
  sample: boolean;
  liveMap: boolean;
  conservativeAvailable: boolean;
}

export type Row = Record<string, string | number | null>;
export interface Audit {
  available: boolean;
  canReview: boolean;
  runs: Row[];
  reviews: Row[];
  alerts: Row[];
}

export interface Weekly {
  history: Row[];
  report: {
    week_end: string;
    checked_at: string;
    notified: string;
    rows: {
      body_id: string;
      name: string;
      state: State;
      alerta: boolean;
      areas: Record<string, { focos: number; normal: number; alerta: boolean }>;
    }[];
  } | null;
}

export const number = (value: number, digits = 0) => new Intl.NumberFormat('es-BO', {
  maximumFractionDigits: digits,
}).format(value);
export const signed = (value: number, digits = 0) => `${value > 0 ? '+' : ''}${number(value, digits)}`;
export const displayDate = (value: string, withDay = true) => new Intl.DateTimeFormat('es-BO', {
  ...(withDay ? { day: 'numeric' } : {}), month: 'long', year: 'numeric', timeZone: 'UTC',
}).format(new Date((value.length === 7 ? value + '-01' : value.slice(0, 10)) + 'T00:00:00Z'));
export const waterChange = (value: number) => value < 0 ? `${number(Math.abs(value), 1)} % menos superficie de agua`
  : value > 0 ? `${number(value, 1)} % más superficie de agua` : 'Sin cambio de superficie de agua';
export const imageUrl = (folder: 'img' | 'context', filename: string) => `/api/images/${folder}/${filename}.png`;
export const modelUrl = (path: string, method: Method) => `${path}?method=${method}`;
export const firstSuspect = (body: WaterBody) => body.suspects?.find((suspect) => !suspect.indirect);

export function visibleStates(method: Method, bodies: WaterBody[]) {
  return [...new Set([...methodStates[method], ...bodies.map((body) => body.state)])];
}

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api/${path}`, { cache: 'no-store', ...options });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.message ?? `La API respondió con el código ${response.status}.`);
  }
  return response.json();
}

export function downloadCsv(rows: Row[]) {
  if (!rows.length) return;
  const columns = Object.keys(rows[0]);
  const cell = (value: string | number | null) => '"' + String(value ?? '').replaceAll('"', '""') + '"';
  const csv = [columns.map(cell).join(','), ...rows.map((row) => columns.map((key) => cell(row[key])).join(','))].join('\r\n');
  const url = URL.createObjectURL(new Blob(['\uFEFF', csv], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'uma_monitoreo.csv';
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
