// components/Dashboard.tsx
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import Header from "./Header";
import FeaturedRegions from "./FeaturedRegions";
import VerdictCard from "./VerdictCard";
import TrendChart from "./TrendChart";
import EmptyState from "./EmptyState";
import PlaybackControls from "./PlaybackControls";
import { useAnalysis } from "@/hooks/useAnalysis";
import { usePlayback } from "@/hooks/usePlayback";
import { getRegions, getVerdicts, getTimeSeries } from "@/lib/api";
import { LEVEL_COLORS, SEVERITY_COLORS } from "@/lib/colors";
import { buildScoreMap } from "@/lib/animation";
import type {
  RegionsFeatureCollection,
  TimeSeriesPayload,
  Verdict,
} from "@/lib/types";

const BoliviaMap = dynamic(() => import("./BoliviaMap"), {
  ssr: false,
  loading: () => (
    <div className="flex h-[500px] items-center justify-center rounded-lg bg-slate-100 md:h-[600px]">
      <span className="animate-pulse-soft text-sm text-slate-500">
        Cargando mapa…
      </span>
    </div>
  ),
});

export default function Dashboard() {
  // ── Estado global ─────────────────────────────────────────────
  const [regions, setRegions] = useState<RegionsFeatureCollection | null>(null);
  const [verdicts, setVerdicts] = useState<Verdict[]>([]);
  const [selectedPcode, setSelectedPcode] = useState<string | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [initialError, setInitialError] = useState<string | null>(null);
  const [timeseries, setTimeseries] = useState<TimeSeriesPayload | null>(null);

  // ── Carga inicial: regions + verdicts en paralelo ─────────────
  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();

    Promise.all([getRegions(controller.signal), getVerdicts(controller.signal)])
      .then(([regionsData, verdictsData]) => {
        if (cancelled) return;
        setRegions(regionsData);
        setVerdicts(verdictsData);
        setInitialLoading(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof DOMException && err.name === "AbortError") return;
        const msg =
          err instanceof Error ? err.message : "Error de conexión desconocido";
        setInitialError(msg);
        setInitialLoading(false);
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, []);

  // ── Carga del timeseries (para playback) ──────────────────────
  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();

    getTimeSeries(controller.signal)
      .then((d) => {
        if (!cancelled) setTimeseries(d);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof DOMException && err.name === "AbortError") return;
        // Timeseries es opcional: si falla, la app sigue sin playback.
        console.warn("[dash] timeseries no disponible:", err);
        setTimeseries(null);
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, []);

  // ── Playback ──────────────────────────────────────────────────
  const totalDekads = timeseries?.dates.length ?? 0;
  const {
    currentDekad,
    isPlaying,
    speed,
    toggle,
    pause,
    seek,
    setSpeed,
  } = usePlayback(totalDekads);

  const scoreByPcode = useMemo(() => {
    if (!timeseries) return null;
    return buildScoreMap(timeseries, currentDekad);
  }, [timeseries, currentDekad]);

  // ── Análisis de la región seleccionada ────────────────────────
  const {
    data: analysis,
    loading: analysisLoading,
    error: analysisError,
  } = useAnalysis(selectedPcode);

  // ── Handlers ──────────────────────────────────────────────────
  const handleSelect = useCallback(
    (pcode: string) => {
      setSelectedPcode(pcode);
      pause(); // detener playback al seleccionar (el usuario quiere ver detalle)
    },
    [pause]
  );

  const handleClose = useCallback(() => {
    setSelectedPcode(null);
  }, []);

  // ── Render ────────────────────────────────────────────────────
  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      <Header />

      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-4">
        {/* Estado 1: error de conexión inicial */}
        {initialError && (
          <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-800">
            <p className="font-semibold">No se pudo conectar con el backend.</p>
            <p className="mt-1 text-xs">
              Verificá que FastAPI esté corriendo en{" "}
              <code className="rounded bg-red-100 px-1 py-0.5">
                http://localhost:8000
              </code>{" "}
              y recargá la página.
            </p>
            <p className="mt-2 text-[11px] text-red-700">{initialError}</p>
          </div>
        )}

        {/* Estado 2: loading inicial */}
        {initialLoading && !initialError && (
          <div className="flex min-h-[400px] items-center justify-center">
            <div className="animate-pulse-soft text-center">
              <div className="mx-auto mb-3 h-10 w-10 rounded-full border-4 border-slate-200 border-t-slate-700" />
              <p className="text-sm font-medium text-slate-600">
                Cargando mapa y veredictos…
              </p>
            </div>
          </div>
        )}

        {/* Estado 3: app lista */}
        {!initialLoading && !initialError && (
          <>
            <div className="mb-3">
              <FeaturedRegions
                verdicts={verdicts}
                selectedPcode={selectedPcode}
                onSelect={handleSelect}
              />
            </div>

            {/* Playback: solo si timeseries cargó */}
            {timeseries && (
              <div className="mb-3">
                <PlaybackControls
                  dates={timeseries.dates}
                  currentDekad={currentDekad}
                  isPlaying={isPlaying}
                  speed={speed}
                  onToggle={toggle}
                  onSeek={seek}
                  onSetSpeed={setSpeed}
                />
              </div>
            )}

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
              {/* Columna izquierda: mapa */}
              <section className="lg:col-span-7">
                <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
                  <BoliviaMap
                    regions={regions}
                    verdicts={verdicts}
                    selectedPcode={selectedPcode}
                    onSelect={handleSelect}
                    scoreByPcode={scoreByPcode}
                  />
                </div>

                {/* Leyenda: cambia según el modo (playback vs estático) */}
                <div className="mt-2 flex flex-wrap items-center gap-3 px-1 text-[11px] text-slate-600">
                  {scoreByPcode ? (
                    <>
                      <span className="font-medium text-slate-700">
                        Score compuesto:
                      </span>
                      <span className="inline-flex items-center gap-1">
                        <span
                          className="inline-block h-2.5 w-2.5 rounded-sm"
                          style={{ backgroundColor: SEVERITY_COLORS.low }}
                        />
                        <span>Normal</span>
                      </span>
                      <span className="inline-flex items-center gap-1">
                        <span
                          className="inline-block h-2.5 w-2.5 rounded-sm"
                          style={{ backgroundColor: SEVERITY_COLORS.moderate }}
                        />
                        <span>Moderado</span>
                      </span>
                      <span className="inline-flex items-center gap-1">
                        <span
                          className="inline-block h-2.5 w-2.5 rounded-sm"
                          style={{ backgroundColor: SEVERITY_COLORS.high }}
                        />
                        <span>Alto</span>
                      </span>
                      <span className="inline-flex items-center gap-1">
                        <span
                          className="inline-block h-2.5 w-2.5 rounded-sm"
                          style={{ backgroundColor: SEVERITY_COLORS.extreme }}
                        />
                        <span>Extremo</span>
                      </span>
                      <span className="inline-flex items-center gap-1">
                        <span
                          className="inline-block h-2.5 w-2.5 rounded-sm"
                          style={{ backgroundColor: "#9ca3af" }}
                        />
                        <span>Sin datos</span>
                      </span>
                    </>
                  ) : (
                    (
                      ["crisis", "alert", "watch", "stable", "no_data"] as const
                    ).map((lvl) => (
                      <span
                        key={lvl}
                        className="inline-flex items-center gap-1"
                      >
                        <span
                          className="inline-block h-2.5 w-2.5 rounded-sm"
                          style={{ backgroundColor: LEVEL_COLORS[lvl] }}
                        />
                        <span className="capitalize">
                          {lvl.replace("_", " ")}
                        </span>
                      </span>
                    ))
                  )}
                </div>
              </section>

              {/* Columna derecha: veredicto + gráficos */}
              <section className="flex flex-col gap-3 lg:col-span-5">
                {!selectedPcode && <EmptyState />}

                {selectedPcode && analysisLoading && (
                  <div className="flex min-h-[300px] items-center justify-center rounded-lg border border-slate-200 bg-white">
                    <div className="animate-pulse-soft text-center">
                      <div className="mx-auto mb-3 h-8 w-8 rounded-full border-4 border-slate-200 border-t-slate-700" />
                      <p className="text-sm text-slate-600">
                        Analizando región…
                      </p>
                    </div>
                  </div>
                )}

                {selectedPcode && !analysisLoading && analysisError && (
                  <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-800">
                    <p className="font-semibold">
                      No se pudo cargar el análisis.
                    </p>
                    <p className="mt-1 text-xs">{analysisError}</p>
                  </div>
                )}

                {selectedPcode && !analysisLoading && analysis && (
                  <>
                    <VerdictCard analysis={analysis} onClose={handleClose} />
                    <TrendChart
                      title="Precipitación (r3h)"
                      color="#2563eb"
                      stats={analysis.rainfall}
                    />
                    <TrendChart
                      title="NDVI (vim)"
                      color="#16a34a"
                      stats={analysis.ndvi}
                    />
                  </>
                )}
              </section>
            </div>
          </>
        )}
      </main>

      <footer className="border-t border-slate-200 bg-white px-4 py-3 text-center text-[11px] text-slate-500">
        MVP hackatón · Datos dekadales ADM2 · Mann-Kendall + Sen&apos;s slope ·
        Lag 0–3 dekads
      </footer>
    </div>
  );
}