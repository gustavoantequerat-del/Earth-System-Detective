import type { FeatureCollection, MultiPolygon, Polygon } from 'geojson';

export const levels = {
  crisis: { label: 'Crisis', color: [248, 101, 131] },
  alert: { label: 'Alerta de lluvia', color: [255, 151, 103] },
  watch: { label: 'Investigar vegetación', color: [255, 211, 114] },
  stable: { label: 'Estable', color: [102, 214, 161] },
  no_data: { label: 'Sin datos', color: [135, 151, 173] },
} as const;

export const severity = {
  low: { label: 'Normal', color: [102, 214, 161] },
  moderate: { label: 'Moderada', color: [255, 211, 114] },
  high: { label: 'Alta', color: [255, 151, 103] },
  extreme: { label: 'Extrema', color: [248, 101, 131] },
} as const;

export type Level = keyof typeof levels;
export type Severity = keyof typeof severity;
export type Region = { pcode: string; name: string; adm1_name: string };
export type Verdict = Region & { level: Level; verdict: string; n_pixels: number };
export type RegionLayer = 'trend' | 'joint' | 'rain' | 'ndvi';

export interface Atlas {
  origin: string;
  from: string;
  to: string;
  verdicts: Verdict[];
  geometry: FeatureCollection<Polygon | MultiPolygon, Region>;
}

export interface RegionalTimeline {
  dates: string[];
  regions: Record<string, Omit<Region, 'pcode'> & { r3q: (number | null)[]; viq: (number | null)[] }>;
}

export interface RegionalTrend {
  variable: string; unit: string; slope: number | null; p_value: number | null; trend: string; significant: boolean; n_obs: number;
  series: { date: string; value: number }[];
  anomaly_series: { date: string; value: number }[];
  climatology: { dekad: number; lta: number }[] | null;
}

export interface RegionalWindow {
  start: string; end: string; rainfall_anomaly_pct: number | null; ndvi_anomaly_pct: number | null; compound_severity: Severity;
}
export interface Analysis extends Verdict {
  explanation: string;
  period: { start: string; end: string };
  rainfall: RegionalTrend;
  ndvi: RegionalTrend;
  correlation: { r: number | null; p_value: number | null; lag_dekads: number | null; significant: boolean };
  windows: (RegionalWindow & { label: string; evidence: string })[];
  worst_period: (RegionalWindow & { explanation: string }) | null;
}

export const severityFor = (value: number): Severity => value < -40 ? 'extreme' : value < -25 ? 'high' : value < -10 ? 'moderate' : 'low';
