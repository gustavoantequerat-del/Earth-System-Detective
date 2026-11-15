import Image from 'next/image';
import Link from 'next/link';
import type { ReactNode } from 'react';
import { ArrowDown, ArrowRight, ArrowUpRight, Droplets, Flame, Leaf } from 'lucide-react';

export function MissionHome({ lakes, fires, vegetation, alerts }: { lakes: string; fires: string; vegetation: string; alerts: ReactNode }) {
  const topics = [
    { href: lakes, name: 'Lagos', icon: Droplets, media: 'titicaca', alt: 'Lago Menor del Titicaca visto desde Landsat',
      description: 'Explora el relieve en 3D, compara la superficie de agua y abre la ficha de cada caso.' },
    { href: fires, name: 'Incendios', icon: Flame, media: 'chiquitania', alt: 'Imagen del este de la Chiquitania',
      description: 'Consulta los focos térmicos por cuenca y compáralos con el promedio histórico de la semana.' },
    { href: vegetation, name: 'Vegetación', icon: Leaf, media: 'san-matias', alt: 'Mapa de cambios de cobertura en San Matías',
      description: 'Compara lluvia y verdor por provincia y revisa el bosque, los cultivos y las pasturas alrededor de los lagos.' },
  ];

  return <>
    <section className="mission-hero" aria-labelledby="mission-title">
      <div className="mission-hero-media">
        <Image src="/observations/poopo.webp" alt="" fill preload sizes="100vw" unoptimized />
      </div>
      <div className="mission-hero-scrim" aria-hidden="true" />
      <div className="mission-hero-inner">
        <div className="mission-hero-copy">
          <p className="mission-eyebrow">Agua de Bolivia</p>
          <h1 id="mission-title">Detector de<br /><span className="mission-marker">huella humana</span></h1>
          <p>Observa cómo cambian los lagos de Bolivia y qué señales dejan el clima, los incendios y el uso del suelo en sus cuencas.</p>
          <div className="mission-hero-actions">
            <a className="button-link primary" href="#alertas">Ver alertas <ArrowDown size={19} aria-hidden="true" /></a>
            <Link className="mission-anchor" href={lakes}>Explorar lagos <ArrowUpRight size={17} aria-hidden="true" /></Link>
          </div>
        </div>
        <p className="mission-image-credit">Lago Poopó, Bolivia <span>Landsat · 2023</span></p>
      </div>
    </section>
    {alerts}
    <section id="explorar" className="mission-topics" tabIndex={-1}>
      <div className="mission-section-heading">
        <h2>Explora las cuencas</h2>
        <p>Elige qué observar en el agua y a su alrededor.</p>
      </div>
      <div className="mission-topic-grid">
        {topics.map(({ href, name, icon: Icon, media, alt, description }) => <Link key={name} href={href} className={`mission-topic topic-${media}`}>
          <Image src={`/observations/${media}.webp`} alt={alt} fill sizes="(max-width: 700px) 75vw, 33vw" unoptimized />
          <div className="mission-topic-content">
            <Icon aria-hidden="true" size={23} />
            <h3>{name}</h3>
            <p>{description}</p>
            <ArrowRight className="topic-arrow" aria-hidden="true" size={22} />
          </div>
        </Link>)}
      </div>
    </section>
  </>;
}
