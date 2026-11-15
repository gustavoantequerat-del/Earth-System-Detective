// components/Header.tsx
// Header oscuro global. No usa estado, es Server-Component friendly
// (aunque el árbol lo fuerza a cliente por el Dashboard padre).

export default function Header() {
  return (
    <header className="bg-slate-900 text-white">
      <div className="mx-auto flex max-w-7xl flex-col gap-2 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
        <div className="flex items-baseline gap-3">
          <h1 className="text-lg font-bold tracking-tight sm:text-xl">
            Earth System Trend Detective
          </h1>
          <span className="rounded bg-slate-700 px-2 py-0.5 text-xs font-medium text-slate-200">
            Bolivia
          </span>
        </div>

        <a
          href="https://www.spaceappschallenge.org/"
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-slate-300 underline-offset-4 hover:text-white hover:underline"
        >
          NASA Space Apps 2026 ↗
        </a>
      </div>
    </header>
  );
}