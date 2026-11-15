// components/PlaybackControls.tsx
// Versión controlada: el padre maneja currentDekad.
// Este componente solo dispara onSeek/onToggle.

"use client";

interface PlaybackControlsProps {
  dates: string[];
  currentDekad: number;
  isPlaying: boolean;
  speed: 1 | 2 | 4;
  onToggle: () => void;
  onSeek: (index: number) => void;
  onSetSpeed: (s: 1 | 2 | 4) => void;
}

export default function PlaybackControls({
  dates,
  currentDekad,
  isPlaying,
  speed,
  onToggle,
  onSeek,
  onSetSpeed,
}: PlaybackControlsProps) {
  const currentDate = dates[currentDekad] ?? "";

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-slate-200 bg-white p-3">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onToggle}
          aria-label={isPlaying ? "Pausar" : "Reproducir"}
          className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-slate-900 text-white hover:bg-slate-700"
        >
          <span aria-hidden="true" className="text-lg leading-none">
            {isPlaying ? "❚❚" : "▶"}
          </span>
        </button>

        <input
          type="range"
          min={0}
          max={Math.max(0, dates.length - 1)}
          value={currentDekad}
          onChange={(e) => onSeek(Number(e.target.value))}
          className="flex-1 accent-slate-900"
          aria-label="Dekad"
        />

        <span className="w-20 text-right font-mono text-xs text-slate-700">
          {currentDate.slice(0, 7)}
        </span>
      </div>

      <div className="flex items-center justify-between text-[11px] text-slate-500">
        <span>
          {currentDekad + 1} / {dates.length} dekads
        </span>
        <div className="flex items-center gap-1">
          <span className="mr-1">Velocidad:</span>
          {([1, 2, 4] as const).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => onSetSpeed(s)}
              className={`rounded px-2 py-0.5 ${
                speed === s
                  ? "bg-slate-900 text-white"
                  : "bg-slate-100 text-slate-700 hover:bg-slate-200"
              }`}
            >
              {s}×
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}