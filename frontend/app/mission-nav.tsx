'use client';

import { useId } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ChevronDown, Droplets, Flame, House, Leaf, Waves } from 'lucide-react';
import { LayoutGroup, motion, useReducedMotion } from 'motion/react';

const destinations = [
  { key: 'inicio', label: 'Inicio', Icon: House },
  { key: 'agua', label: 'Cuerpos de agua', Icon: Droplets },
  { key: 'incendios', label: 'Incendios', Icon: Flame },
  { key: 'vegetacion', label: 'Vegetación', Icon: Leaf },
] as const;

export const waterModules = {
  lagos: { label: 'Lagos', Icon: Droplets },
  rios: { label: 'Ríos', Icon: Waves },
} as const;
export type WaterModule = keyof typeof waterModules;
type Section = typeof destinations[number]['key'];
type Links = Record<Exclude<Section, 'agua'> | WaterModule, string>;

function Sphere({ id, Icon, reducedMotion }: { id: string; Icon: typeof House; reducedMotion: boolean | null }) {
  return <motion.span aria-hidden="true" className="mission-sphere"
    layoutId={reducedMotion ? undefined : 'nav-sphere'} transition={{ type: 'spring', stiffness: 300, damping: 30 }}>
    <svg viewBox="0 0 120 80" focusable="false">
      <defs>
        <linearGradient id={id + '-bubble'} x1="32" y1="8" x2="88" y2="72" gradientUnits="userSpaceOnUse">
          <stop stopColor="#a7f3e4" /><stop offset=".48" stopColor="#0f9d8f" /><stop offset="1" stopColor="#0b4f5c" />
        </linearGradient>
        <radialGradient id={id + '-shine'} cx="0" cy="0" r="1" gradientTransform="translate(50 28) rotate(58) scale(29)">
          <stop stopColor="white" stopOpacity=".65" /><stop offset="1" stopColor="white" stopOpacity="0" />
        </radialGradient>
      </defs>
      <path d="M0 66H12C22 66 27 62 29 53C31 47 30 40 32 32C36 17 46 8 60 8C74 8 84 17 88 32C90 40 89 47 91 53C93 62 98 66 108 66H120Z" fill="#0d2a31" />
      <circle cx="60" cy="44" r="25" fill={`url(#${id}-bubble)`} stroke="#d5fbf3" strokeOpacity=".48" />
      <circle cx="60" cy="44" r="24" fill={`url(#${id}-shine)`} />
    </svg>
    <Icon size={17} strokeWidth={2.2} />
  </motion.span>;
}

export function MissionNav({ active, water, links }: { active: Section; water: WaterModule; links: Links }) {
  const id = useId();
  const router = useRouter();
  const reducedMotion = useReducedMotion();
  return <header className="mission-header">
    <div className="mission-navbar">
      <Link className="mission-brand" href={links.inicio} aria-label="Ir al inicio del Detector de huella humana">
        <Image src="/brand/nasa-space-apps.svg" alt="NASA Space Apps Challenge" width={136} height={47} unoptimized />
      </Link>
      <nav className="mission-nav" aria-label="Navegación principal">
        <LayoutGroup id={id}>
          {destinations.map(({ key, label, Icon }) => {
            const current = key === active;
            if (key === 'agua') {
              const ModuleIcon = waterModules[water].Icon;
              return <div key={key} className="mission-nav-select" data-current={current || undefined}>
                {current ? <Sphere id={id} Icon={ModuleIcon} reducedMotion={reducedMotion} />
                  : <ModuleIcon aria-hidden="true" size={17} className="mission-nav-icon" />}
                <label>
                  <span className="mission-nav-select-label">{label}</span>
                  <select aria-label="Elegir el tipo de cuerpo de agua" value={current ? water : ''}
                    onChange={(event) => router.push(links[event.target.value as WaterModule])}>
                    {!current && <option value="" disabled>Lagos o ríos</option>}
                    {(Object.keys(waterModules) as WaterModule[]).map((module) =>
                      <option key={module} value={module}>{waterModules[module].label}</option>)}
                  </select>
                  <ChevronDown aria-hidden="true" size={15} className="mission-nav-chevron" />
                </label>
              </div>;
            }
            return <Link key={key} href={links[key]} aria-current={current ? 'page' : undefined}>
              {current && <Sphere id={id} Icon={Icon} reducedMotion={reducedMotion} />}
              {!current && <Icon aria-hidden="true" size={17} className="mission-nav-icon" />}
              <span>{label}</span>
            </Link>;
          })}
        </LayoutGroup>
      </nav>
    </div>
  </header>;
}
