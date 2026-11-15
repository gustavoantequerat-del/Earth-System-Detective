'use client';

import { useEffect, useId, useRef, useState } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { Check, ChevronDown, Droplets, Flame, House, Leaf, Waves } from 'lucide-react';
import { motion, useReducedMotion } from 'motion/react';

export const waterModules = {
  lagos: { label: 'Lagos', Icon: Droplets, description: 'Diagnóstico de cada lago: cuánta agua perdió y por qué.' },
  rios: { label: 'Ríos', Icon: Waves, description: 'El Desaguadero tramo a tramo: dónde disminuye el agua y qué presiones hay.' },
} as const;
export type WaterModule = keyof typeof waterModules;
type Section = 'inicio' | 'agua' | 'incendios' | 'vegetacion';
type Links = Record<Exclude<Section, 'agua'> | WaterModule, string>;

const plain = [
  { key: 'inicio', label: 'Inicio', Icon: House },
  { key: 'incendios', label: 'Incendios', Icon: Flame },
  { key: 'vegetacion', label: 'Vegetación', Icon: Leaf },
] as const;

function Pill({ reducedMotion }: { reducedMotion: boolean | null }) {
  return <motion.span aria-hidden="true" className="nav-pill" layoutId={reducedMotion ? undefined : 'nav-pill'}
    transition={{ type: 'spring', stiffness: 420, damping: 36 }} />;
}

export function MissionNav({ active, water, links }: { active: Section; water: WaterModule; links: Links }) {
  const menuId = useId();
  const reducedMotion = useReducedMotion();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const inWater = active === 'agua';
  const Current = inWater ? waterModules[water].Icon : Droplets;

  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') { setOpen(false); trigger.current?.focus(); } };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    root.current?.querySelector<HTMLAnchorElement>('[role="menuitem"]')?.focus();
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape); };
  }, [open]);

  const item = (key: typeof plain[number]['key'], label: string, Icon: typeof House) =>
    <Link key={key} href={links[key]} className="nav-item" aria-current={active === key ? 'page' : undefined}>
      {active === key && <Pill reducedMotion={reducedMotion} />}
      <Icon aria-hidden="true" size={18} /><span>{label}</span>
    </Link>;

  return <header className="mission-header">
    <div className="mission-navbar">
      <Link className="mission-brand" href={links.inicio} aria-label="Ir al inicio del Detector de huella humana">
        <Image src="/brand/nasa-space-apps.svg" alt="" width={112} height={39} unoptimized />
        <span className="brand-title"><b>Detector de huella humana</b><small>Observatorio del agua · Bolivia</small></span>
      </Link>
      <nav className="mission-nav" aria-label="Navegación principal">
        {item('inicio', 'Inicio', House)}
        <div className="nav-water" ref={root}>
          <button ref={trigger} type="button" className="nav-item" aria-haspopup="menu" aria-expanded={open} aria-controls={menuId}
            data-current={inWater || undefined} onClick={() => setOpen((value) => !value)}
            onKeyDown={(event) => { if (event.key === 'ArrowDown') { event.preventDefault(); setOpen(true); } }}>
            {inWater && <Pill reducedMotion={reducedMotion} />}
            <Current aria-hidden="true" size={18} />
            <span>{inWater ? waterModules[water].label : 'Lagos y ríos'}</span>
            <ChevronDown aria-hidden="true" size={15} className="nav-chevron" />
          </button>
          {open && <div className="nav-menu" id={menuId} role="menu" aria-label="Cuerpos de agua"
            onKeyDown={(event) => {
              if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
              event.preventDefault();
              const items = [...event.currentTarget.querySelectorAll<HTMLAnchorElement>('[role="menuitem"]')];
              const index = items.indexOf(document.activeElement as HTMLAnchorElement);
              items[(index + (event.key === 'ArrowDown' ? 1 : items.length - 1)) % items.length]?.focus();
            }}>
            <p className="nav-menu-title">Cuerpos de agua</p>
            {(Object.keys(waterModules) as WaterModule[]).map((module) => {
              const { label, Icon, description } = waterModules[module];
              const selected = inWater && module === water;
              return <Link key={module} role="menuitem" href={links[module]} className="nav-menu-item"
                aria-current={selected ? 'page' : undefined} onClick={() => setOpen(false)}>
                <span className="nav-menu-icon"><Icon size={19} aria-hidden="true" /></span>
                <span><b>{label}</b><small>{description}</small></span>
                {selected && <Check size={17} aria-hidden="true" className="nav-menu-check" />}
              </Link>;
            })}
          </div>}
        </div>
        {plain.slice(1).map(({ key, label, Icon }) => item(key, label, Icon))}
      </nav>
    </div>
  </header>;
}
