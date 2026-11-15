'use client';

import { useId } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { Droplets, Flame, House, Leaf } from 'lucide-react';
import { LayoutGroup, motion, useReducedMotion } from 'motion/react';

const destinations = [
  { key: 'inicio', label: 'Inicio', Icon: House },
  { key: 'lagos', label: 'Lagos', Icon: Droplets },
  { key: 'incendios', label: 'Incendios', Icon: Flame },
  { key: 'vegetacion', label: 'Vegetación', Icon: Leaf },
] as const;

type Section = typeof destinations[number]['key'];

export function MissionNav({ active, links }: { active: Section; links: Record<Section, string> }) {
  const id = useId();
  const reducedMotion = useReducedMotion();
  return <header className="mission-header">
    <div className="mission-navbar">
      <Link className="mission-brand" href={links.inicio} aria-label="Ir al inicio del Detector de huella humana">
        <Image src="/brand/nasa-space-apps.svg" alt="NASA Space Apps Challenge" width={136} height={47} unoptimized />
      </Link>
      <nav className="mission-nav" aria-label="Navegación principal">
        <LayoutGroup id={id}>
          {destinations.map(({ key, label, Icon }) => <Link key={key} href={links[key]}
            aria-current={key === active ? (key === 'lagos' ? 'location' : 'page') : undefined}>
            {key === active && <motion.span aria-hidden="true" className="mission-sphere"
              layoutId={reducedMotion ? undefined : 'nav-sphere'} transition={{ type: 'spring', stiffness: 300, damping: 30 }}>
              <svg viewBox="0 0 120 80" focusable="false">
                <defs>
                  <linearGradient id={id + '-bubble'} x1="32" y1="8" x2="88" y2="72" gradientUnits="userSpaceOnUse">
                    <stop stopColor="#9bc8ff" /><stop offset=".48" stopColor="#2368ef" /><stop offset="1" stopColor="#162f93" />
                  </linearGradient>
                  <radialGradient id={id + '-shine'} cx="0" cy="0" r="1" gradientTransform="translate(50 28) rotate(58) scale(29)">
                    <stop stopColor="white" stopOpacity=".65" /><stop offset="1" stopColor="white" stopOpacity="0" />
                  </radialGradient>
                </defs>
                <path d="M0 66H12C22 66 27 62 29 53C31 47 30 40 32 32C36 17 46 8 60 8C74 8 84 17 88 32C90 40 89 47 91 53C93 62 98 66 108 66H120Z" fill="#122345" />
                <circle cx="60" cy="44" r="25" fill={`url(#${id}-bubble)`} stroke="#dceaff" strokeOpacity=".48" />
                <circle cx="60" cy="44" r="24" fill={`url(#${id}-shine)`} />
              </svg>
              <Icon size={17} strokeWidth={2.2} />
            </motion.span>}
            {key !== active && <Icon aria-hidden="true" size={17} className="mission-nav-icon" />}
            <span>{label}</span>
          </Link>)}
        </LayoutGroup>
      </nav>
    </div>
  </header>;
}
