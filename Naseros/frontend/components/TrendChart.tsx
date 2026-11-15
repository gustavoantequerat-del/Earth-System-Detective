// components/TrendChart.tsx
// Gráfico de serie temporal + línea de tendencia Sen + (opcional) anomalía %.
// - X-axis type="number" con timestamp en ms (soporta ~850 puntos sin colapsar).
// - Si stats.anomaly_series existe: segundo eje Y derecho + línea dashed de anomalía.
// - Línea observada con strokeOpacity 0.35, tendencia con strokeWidth 2.
// - Sin animación.
// - Subtitle: "✓ decreciente · p = 0.003 · -15.1 mm/década"

"use client";

import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatP, formatSlope, formatTrend, yearFromIso } from "@/lib/formatters";
import type { TrendStats } from "@/lib/types";

interface TrendChartProps {
  title: string;
  /** Color de la línea observada (y de la tendencia). */
  color: string;
  stats: TrendStats;
  /** Altura del gráfico en px. Default 240. */
  height?: number;
}

interface ChartPoint {
  /** Timestamp en ms, para que Recharts type="number" funcione bien. */
  t: number;
  value: number | null;
  /** Valor de la tendencia Sen en esa fecha (recta anclada a la media). */
  trend: number;
  /** Anomalía % si el backend la expone; null si no aplica. */
  anomaly: number | null;
}

export default function TrendChart({
  title,
  color,
  stats,
  height = 240,
}: TrendChartProps) {
  // ¿Mostramos el eje derecho y la línea de anomalía?
  const hasAnomaly =
    Array.isArray(stats.anomaly_series) && stats.anomaly_series.length > 0;

  // Construir datos del chart + recta de tendencia anclada a la media.
  const data = useMemo<ChartPoint[]>(() => {
    const series = stats.series;
    if (series.length === 0) return [];

    // slope está en unidades/dekad; convertimos a unidades/ms.
    const DEKAD_MS = 10 * 24 * 60 * 60 * 1000; // 10 días en ms
    const slopePerMs = stats.slope / DEKAD_MS;

    const xs: number[] = [];
    const ys: number[] = [];
    for (const p of series) {
      if (p.value == null) continue;
      xs.push(new Date(p.date).getTime());
      ys.push(p.value);
    }

    // Mapa fecha→anomalía (opcional).
    const anomalyByDate = new Map<string, number | null>();
    if (hasAnomaly && stats.anomaly_series) {
      for (const p of stats.anomaly_series) {
        anomalyByDate.set(p.date, p.value);
      }
    }

    if (xs.length === 0) {
      return series.map((p) => ({
        t: new Date(p.date).getTime(),
        value: p.value,
        trend: 0,
        anomaly: anomalyByDate.get(p.date) ?? null,
      }));
    }

    const meanX = xs.reduce((a, b) => a + b, 0) / xs.length;
    const meanY = ys.reduce((a, b) => a + b, 0) / ys.length;

    return series.map((p) => {
      const t = new Date(p.date).getTime();
      return {
        t,
        value: p.value,
        trend: meanY + slopePerMs * (t - meanX),
        anomaly: anomalyByDate.get(p.date) ?? null,
      };
    });
  }, [stats, hasAnomaly]);

  const subtitle = [
    formatTrend(stats),
    `p = ${formatP(stats.p_value)}`,
    formatSlope(stats.slope, stats.unit),
  ].join(" · ");

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="mb-1 flex flex-wrap items-baseline justify-between gap-1">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-700">
          {title}
        </h3>
        <span className="text-[11px] text-slate-500">{subtitle}</span>
      </div>

      <div style={{ width: "100%", height }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={data}
            margin={{ top: 6, right: hasAnomaly ? 6 : 12, bottom: 4, left: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis
              dataKey="t"
              type="number"
              domain={["dataMin", "dataMax"]}
              scale="time"
              tickFormatter={(t) =>
                String(yearFromIso(new Date(Number(t)).toISOString()))
              }
              tick={{ fontSize: 10, fill: "#64748b" }}
              stroke="#cbd5e1"
              minTickGap={40}
            />
            <YAxis
              yAxisId="left"
              tick={{ fontSize: 10, fill: "#64748b" }}
              stroke="#cbd5e1"
              width={48}
              domain={["auto", "auto"]}
            />
            {hasAnomaly && (
              <YAxis
                yAxisId="right"
                orientation="right"
                tick={{ fontSize: 10, fill: "#7c3aed" }}
                stroke="#c4b5fd"
                width={40}
                domain={["auto", "auto"]}
                tickFormatter={(v) => `${Number(v).toFixed(0)}%`}
              />
            )}
            <Tooltip
              contentStyle={{
                fontSize: 11,
                borderRadius: 6,
                border: "1px solid #cbd5e1",
              }}
              labelFormatter={(t) =>
                new Date(Number(t)).toISOString().slice(0, 10)
              }
              formatter={(value, name) => {
                const v = typeof value === "number" ? value : Number(value);
                const label =
                  name === "trend"
                    ? "Tendencia Sen"
                    : name === "anomaly"
                    ? "Anomalía"
                    : "Observado";
                if (!Number.isFinite(v)) return ["—", label];
                const decimals = stats.unit === "NDVI" ? 3 : 1;
                const suffix = name === "anomaly" ? " %" : "";
                return [`${v.toFixed(decimals)}${suffix}`, label];
              }}
            />
            {/* Línea observada (más tenue) */}
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="value"
              stroke={color}
              strokeOpacity={0.35}
              strokeWidth={1}
              dot={false}
              isAnimationActive={false}
              connectNulls={false}
              name="value"
            />
            {/* Línea de tendencia (destacada) */}
            <Line
              yAxisId="left"
              type="linear"
              dataKey="trend"
              stroke={color}
              strokeOpacity={1}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              name="trend"
            />
            {/* Anomalía % (opcional, eje derecho, dashed violeta) */}
            {hasAnomaly && (
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="anomaly"
                stroke="#7c3aed"
                strokeOpacity={0.8}
                strokeWidth={1.5}
                strokeDasharray="4 2"
                dot={false}
                isAnimationActive={false}
                connectNulls={false}
                name="anomaly"
              />
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}