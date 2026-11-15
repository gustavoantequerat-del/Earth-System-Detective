// components/DiagnosisTimeline.tsx
// Sección de diagnóstico temporal.
// - Chips por ventana (6m, 12m, 24m, 60m) con severidad compuesta.
// - Tarjeta destacada con worst_period.
// - Si el backend no expone windows/worst_period, no renderiza nada.
// - El orden de las ventanas lo decide el backend; acá solo respetamos.

"use client";

import {
  SEVERITY_BADGE_CLASSES,
  SEVERITY_COLORS,
  SEVERITY_LABELS,
} from "@/lib/colors";
import { formatAnomalyPct, formatRange } from "@/lib/formatters";
import type { Analysis, WindowDiagnosis } from "@/lib/types";

interface DiagnosisTimelineProps {
  analysis: Analysis;
}

function WindowChip({ w }: { w: WindowDiagnosis }) {
  const color = SEVERITY_COLORS[w.compound_severity];
  return (
    <div
      className="flex flex-col gap-1 rounded-md border bg-white p-2 shadow-sm"
      style={{ borderLeftColor: color, borderLeftWidth: 3 }}
      title={w.evidence}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[11px] font-medium text-slate-700">
          {w.label}
        </span>
        <span
          className={`rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide ${
            SEVERITY_BADGE_CLASSES[w.compound_severity]
          }`}
        >
          {SEVERITY_LABELS[w.compound_severity]}
        </span>
      </div>
      <div className="flex gap-2 text-[10px] text-slate-500">
        <span>
          Lluvia{" "}
          <strong className="text-slate-700">
            {formatAnomalyPct(w.rainfall_anomaly_pct)}
          </strong>
        </span>
        <span>
          NDVI{" "}
          <strong className="text-slate-700">
            {formatAnomalyPct(w.ndvi_anomaly_pct)}
          </strong>
        </span>
      </div>
    </div>
  );
}

export default function DiagnosisTimeline({
  analysis,
}: DiagnosisTimelineProps) {
  const windows = analysis.windows ?? [];
  const worst = analysis.worst_period ?? null;

  if (windows.length === 0 && !worst) return null;

  return (
    <section className="rounded-lg border border-slate-200 bg-slate-50 p-3">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-700">
        Diagnóstico temporal
      </h3>

      {windows.length > 0 && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {windows.map((w, i) => (
            <WindowChip key={`${w.label}-${i}`} w={w} />
          ))}
        </div>
      )}

      {worst && (
        <div
          className="mt-3 rounded-md border bg-white p-2.5"
          style={{ borderColor: SEVERITY_COLORS[worst.compound_severity] }}
        >
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-medium uppercase tracking-wide text-slate-500">
                Peor período
              </span>
              <span
                className={`rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide ${
                  SEVERITY_BADGE_CLASSES[worst.compound_severity]
                }`}
              >
                {SEVERITY_LABELS[worst.compound_severity]}
              </span>
            </div>
            <span className="text-[11px] font-semibold text-slate-700">
              {formatRange(worst.start, worst.end)}
            </span>
          </div>
          <div className="mt-1 flex gap-3 text-[10px] text-slate-600">
            <span>
              Lluvia{" "}
              <strong className="text-slate-800">
                {formatAnomalyPct(worst.rainfall_anomaly_pct)}
              </strong>
            </span>
            <span>
              NDVI{" "}
              <strong className="text-slate-800">
                {formatAnomalyPct(worst.ndvi_anomaly_pct)}
              </strong>
            </span>
          </div>
          <p className="mt-1.5 text-[11px] leading-relaxed text-slate-600">
            {worst.explanation}
          </p>
        </div>
      )}
    </section>
  );
}