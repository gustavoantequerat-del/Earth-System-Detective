import Image from 'next/image';
import Link from 'next/link';
import type { ReactNode } from 'react';
import { ArrowDown, ArrowRight, ArrowUpRight, ClipboardCheck, Droplets, FileDown, Flame, Leaf, Scale, Waves } from 'lucide-react';

export function MissionHome({ lakes, rivers, fires, vegetation, alerts }: {
  lakes: string; rivers: string; fires: string; vegetation: string; alerts: ReactNode;
}) {
  const topics = [
    { href: lakes, name: 'Lagos', icon: Droplets, media: 'titicaca', alt: 'Lago Menor del Titicaca visto desde Landsat',
      description: 'Cuánta agua perdió cada lago, qué la explica y qué tan seguro es el diagnóstico.' },
    { href: rivers, name: 'Ríos', icon: Waves, media: 'poopo', alt: 'Lago Poopó y el río Desaguadero desde Landsat',
      description: 'El Desaguadero tramo a tramo: dónde se pierde el agua y qué obras hay en el camino.' },
    { href: fires, name: 'Incendios', icon: Flame, media: 'chiquitania', alt: 'Imagen del este de la Chiquitania',
      description: 'Focos de calor por cuenca comparados con lo habitual para cada semana del año.' },
    { href: vegetation, name: 'Vegetación', icon: Leaf, media: 'san-matias', alt: 'Mapa de cambios de cobertura en San Matías',
      description: 'Lluvia y verdor por provincia; bosque, cultivos y pasturas alrededor de los lagos.' },
  ];
  const values = [
    { icon: ClipboardCheck, title: 'Prioriza inspecciones', text: 'Ordena los cuerpos de agua por gravedad y señala qué actividad revisar primero en cada cuenca.' },
    { icon: Scale, title: 'Evidencia defendible', text: 'Cada veredicto separa clima, aguas arriba y actividad humana, con su nivel de confianza y sus límites.' },
    { icon: FileDown, title: 'Datos abiertos y trazables', text: 'Fuentes públicas (NASA, USGS, MapBiomas, OpenStreetMap), controles de calidad visibles y descargas en CSV.' },
  ];

  return <>
    <section className="mission-hero" aria-labelledby="mission-title">
      <div className="mission-hero-media">
        <Image src="/observations/poopo.webp" alt="" fill preload sizes="100vw" unoptimized />
      </div>
      <div className="mission-hero-scrim" aria-hidden="true" />
      <div className="mission-hero-inner">
        <div className="mission-hero-copy">
          <p className="mission-eyebrow">Observatorio del agua de Bolivia</p>
          <h1 id="mission-title">Detector de<br /><span className="mission-marker">huella humana</span></h1>
          <p>Evidencia satelital para autoridades del agua, ONG y organismos de cooperación: qué lagos y ríos pierden agua, por qué, y dónde actuar primero.</p>
          <div className="mission-hero-actions">
            <a className="button-link primary" href="#alertas">Ver alertas <ArrowDown size={19} aria-hidden="true" /></a>
            <Link className="mission-anchor" href={lakes}>Explorar lagos <ArrowUpRight size={17} aria-hidden="true" /></Link>
            <Link className="mission-anchor" href={rivers}>Seguir el río <ArrowUpRight size={17} aria-hidden="true" /></Link>
          </div>
        </div>
        <p className="mission-image-credit">Lago Poopó, Bolivia <span>Landsat · 2023</span></p>
      </div>
    </section>
    <section className="mission-values" aria-label="Para qué sirve el observatorio">
      {values.map(({ icon: Icon, title, text }) => <article key={title}>
        <Icon size={24} aria-hidden="true" /><div><h2>{title}</h2><p>{text}</p></div>
      </article>)}
    </section>
    {alerts}
    <section id="explorar" className="mission-topics" tabIndex={-1}>
      <div className="mission-section-heading">
        <h2>Explora las cuencas</h2>
        <p>Elige qué observar en el agua y a su alrededor.</p>
      </div>
      <div className="mission-topic-grid">
        {topics.map(({ href, name, icon: Icon, media, alt, description }) => <Link key={name} href={href} className={`mission-topic topic-${media}`}>
          <Image src={`/observations/${media}.webp`} alt={alt} fill sizes="(max-width: 700px) 75vw, 25vw" unoptimized />
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
