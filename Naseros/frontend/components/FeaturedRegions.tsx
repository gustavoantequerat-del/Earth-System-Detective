// components/FeaturedRegions.tsx
// Chips de acceso rápido a dos regiones destacadas:
//   - Chaco (Tarija): prioriza crisis > alert > watch
//   - Altiplano (Oruro): prioriza stable > alert > watch
// Ambos caen al primer veredicto si ninguno matchea la prioridad.

"use client";

import { useMemo } from "react";
import { LEVEL_COLORS, LEVEL_LABELS } from "@/lib/colors";
import type { Level, Verdict } from "@/lib/types";

interface FeaturedRegionsProps {
  verdicts: Verdict[];
  selectedPcode: string | null;
  onSelect: (pcode: string) => void;
}

/** Orden de prioridad por chip. Menor índice = más prioritario. */
const CHACO_PRIORITY: Level[] = ["crisis", "alert", "watch"];
const ALTIPLANO_PRIORITY: Level[] = ["stable", "alert", "watch"];

function pickByPriority(
  verdicts: Verdict[],
  adm1: string,
  priority: Level[]
): Verdict | null {
  const candidates = verdicts.filter((v) => v.adm1_name === adm1);
  if (candidates.length === 0) return null;

  for (const level of priority) {
    const match = candidates.find((v) => v.level === level);
    if (match) return match;
  }

  // Fallback: primer veredicto de la región si ninguno matchea prioridad.
  return candidates[0];
}

interface ChipData {
  key: "chaco" | "altiplano";
  label: string;
  verdict: Verdict | null;
}

export default function FeaturedRegions({
  verdicts,
  selectedPcode,
  onSelect,
}: FeaturedRegionsProps) {
  const chips = useMemo<ChipData[]>(() => {
    return [
      {
        key: "chaco",
        label: "Chaco (Tarija)",
        verdict: pickByPriority(verdicts, "Tarija", CHACO_PRIORITY),
      },
      {
        key: "altiplano",
        label: "Altiplano (Oruro)",
        verdict: pickByPriority(verdicts, "Oruro", ALTIPLANO_PRIORITY),
      },
    ];
  }, [verdicts]);

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="mr-1 text-xs font-medium uppercase tracking-wide text-slate-500">
        Accesos rápidos:
      </span>

      {chips.map((chip) => {
        const v = chip.verdict;
        const disabled = !v;
        const isActive = v && v.pcode === selectedPcode;
        const color = v ? LEVEL_COLORS[v.level] : "#9ca3af";

        return (
          <button
            key={chip.key}
            type="button"
            disabled={disabled}
            onClick={() => v && onSelect(v.pcode)}
            title={
              v
                ? `${v.name} (${v.adm1_name}) · ${LEVEL_LABELS[v.level]}`
                : "Sin datos disponibles"
            }
            className={[
              "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
              disabled
                ? "cursor-not-allowed border-slate-200 bg-slate-100 text-slate-400"
                : "cursor-pointer border-slate-300 bg-white text-slate-700 hover:border-slate-400 hover:bg-slate-50",
              isActive ? "ring-2 ring-slate-900 ring-offset-1" : "",
            ].join(" ")}
          >
            <span
              aria-hidden="true"
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: color }}
            />
            <span>{chip.label}</span>
            {v && (
              <span className="text-[10px] uppercase tracking-wide text-slate-500">
                {LEVEL_LABELS[v.level]}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}