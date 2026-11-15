export const waterThreshold = 10;
export const waterPriority = 30;

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
  state?: string;
  area?: string;
}

export interface WeeklyRecord {
  week_end: string;
  checked_at: string;
  notified: string;
  rows: {
    body_id: string; name: string; state: string; alerta: boolean;
    areas: Record<string, { focos: number; normal: number; alerta: boolean }>;
  }[];
}

export const isDrill = (report: WeeklyRecord) => /simulacro|dry.run/i.test(report.notified ?? '');

export function median(values: number[]) {
  const list = [...values].sort((a, b) => a - b);
  const middle = list.length >> 1;
  return list.length % 2 ? list[middle] : (list[middle - 1] + list[middle]) / 2;
}
