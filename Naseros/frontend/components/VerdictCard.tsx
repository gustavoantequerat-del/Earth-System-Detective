// components/VerdictCard.tsx
// Tarjeta con el veredicto de la región seleccionada.
// - Borde del color del level.
// - Badge con label.
// - Explanation en lenguaje natural.
// - Grid de métricas (p lluvia, p NDVI, Sen lluvia, Sen NDVI, r, lag).
// - Footer con n_pixels y periodo.
// - Botón × para cerrar (vuelve a EmptyState vía onClose).

"use client";

import {
  LEVEL_BADGE_CLASSES,
  LEVEL_COLORS,
  LEVEL_LABELS,
} from "@/lib/colors";
import {
  formatLag,
  formatP,
  formatSlope,
  shortDate,
} from "@/lib/formatters";
import type { Analysis } from "@/lib/types";

interface VerdictCardProps {
  analysis: Analysis;
  onClose: () => void;
}

interface MetricProps {
  label: string;
  value: string;
}

function Metric({ label, value }: MetricProps) {
  return (
    <div className="rounded-md bg-slate-50 px-3 py-2">
      <div className="text-[10px] font-medium uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="mt-0.5 text-sm font-semibold text-slate-900">{value}</div>
    </div>
  );
}

export default function VerdictCard({ analysis, onClose }: VerdictCardProps) {
  const { rainfall, ndvi, correlation } = analysis;
  const borderColor = LEVEL_COLORS[analysis.level];

  return (
    <article
      className="relative rounded-lg border-l-4 bg-white p-4 shadow-sm"
      style={{ borderLeftColor: borderColor }}
    >
      {/* Botón cerrar */}
      <button
        type="button"
        onClick={onClose}
        aria-label="Cerrar veredicto"
        className="absolute right-2 top-2 inline-flex h-7 w-7 items-center justify-center rounded-md text-slate-400 hover:bg-slate-100 hover:text-slate-700"
      >
        <span aria-hidden="true" className="text-lg leading-none">
          ×
        </span>
      </button>

      {/* Título + badge */}
      <div className="pr-8">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <span
            className={`inline-block rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${LEVEL_BADGE_CLASSES[analysis.level]}`}
          >
            {LEVEL_LABELS[analysis.level]}
          </span>
          <span className="text-xs text-slate-500">
            {analysis.name} · {analysis.adm1_name}
          </span>
        </div>
        <h2 className="text-sm font-semibold leading-snug text-slate-900">
          {analysis.verdict}
        </h2>
      </div>

      {/* Explanation */}
      <p className="mt-2 text-xs leading-relaxed text-slate-600">
        {analysis.explanation}
      </p>

      {/* Grid de métricas */}
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
        <Metric label="p lluvia" value={formatP(rainfall.p_value)} />
        <Metric label="p NDVI" value={formatP(ndvi.p_value)} />
        <Metric
          label="Sen lluvia"
          value={formatSlope(rainfall.slope, rainfall.unit)}
        />
        <Metric label="Sen NDVI" value={formatSlope(ndvi.slope, ndvi.unit)} />
        <Metric
          label="Correlación r"
          value={Number.isFinite(correlation.r) ? correlation.r.toFixed(2) : "—"}
        />
        <Metric label="Lag" value={formatLag(correlation.lag_dekads)} />
      </div>

      {/* Footer */}
      <div className="mt-3 flex items-center justify-between border-t border-slate-100 pt-2 text-[11px] text-slate-500">
        <span>{analysis.n_pixels} píxeles</span>
        <span>
          {shortDate(analysis.period.start)}–{shortDate(analysis.period.end)}
        </span>
      </div>
    </article>
  );
}