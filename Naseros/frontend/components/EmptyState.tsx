// components/EmptyState.tsx
// Placeholder cuando no hay región seleccionada.

export default function EmptyState() {
  return (
    <div className="flex h-full min-h-[300px] flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed border-slate-300 bg-slate-50 p-8 text-center">
      <span className="text-4xl" role="img" aria-label="Lupa">
        🔍
      </span>
      <p className="text-sm font-medium text-slate-700">
        Selecciona una provincia
      </p>
      <p className="max-w-xs text-xs text-slate-500">
        Haz clic en el mapa o usa los accesos rápidos para ver el análisis de
        tendencia.
      </p>
    </div>
  );
}