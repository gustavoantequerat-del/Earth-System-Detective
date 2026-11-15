'use client';

import { useEffect, useRef, useState } from 'react';
import { ArrowDown, ArrowLeft, ArrowRight, CircleHelp, Compass, X } from 'lucide-react';

const guides = {
  panorama: [
    { title: 'Revisa las alertas', text: 'Las tarjetas indican qué lago o cuenca merece revisión, cuándo cambió y qué fuente lo registró.', target: 'watch-title' },
    { title: 'Elige qué explorar', text: 'Lagos reúne el mapa, la tabla y las fichas. Incendios muestra focos térmicos. Vegetación explica qué cambió en el suelo alrededor del agua.', target: 'explorar' },
    { title: 'Lee los diagnósticos en conjunto', text: 'El gráfico muestra cuántos cuerpos de agua hay en cada categoría. Puedes elegir entre el análisis completo y el barrido nacional.', target: 'diagnosticos-inicio' },
    { title: 'Abre un caso', text: 'Cada caso reúne el cambio en la superficie de agua y su diagnóstico. Entra a la ficha para ver imágenes y pruebas.', target: 'casos-lagos' },
  ],
  mapa: [
    { title: 'Encuentra un lago por nombre', text: 'Escribe Poopó, Titicaca u otro nombre. Elige un resultado y el mapa se acercará al lugar.', target: 'buscar-lago' },
    { title: 'Lee el mapa', text: 'Las gotas señalan lagos con ficha completa. Pasa el mouse para leer el cambio de agua y el diagnóstico. En celular, toca la gota o el punto.', target: 'mapa-lagos' },
    { title: 'Entiende los colores', text: 'Cada color representa un diagnóstico. Pasa el mouse por la tarjeta o tócala para ver qué significa esa categoría.', target: 'diagnosticos-map' },
  ],
  monitoreo: [
    { title: 'Busca o filtra la tabla', text: 'Escribe el nombre y usa los filtros para ver solo un diagnóstico o un tipo de análisis.', target: 'filtros-monitoreo' },
    { title: 'Lleva los datos contigo', text: 'Descargar CSV guarda las filas que ves después de aplicar los filtros. Los nombres con flecha abren una ficha completa.', target: 'datos-monitoreo' },
  ],
  ficha: [
    { title: 'Empieza por el resumen', text: 'Mira cuánto cambió la superficie del lago. El texto debajo del diagnóstico cuenta lo que las pruebas permiten concluir.', target: 'resumen-ficha' },
    { title: 'Observa los cambios desde satélite', text: 'En «Antes y después», arrastra el control de la imagen. Puedes cambiar las fechas o mirar el lago y sus alrededores.', target: 'secciones-ficha' },
    { title: 'Consulta las pruebas', text: 'Abre «Pruebas y posibles causas» para ver qué se evaluó. En «Auditoría» está el historial técnico de revisiones y resultados.', target: 'secciones-ficha' },
  ],
  vigilancia: [
    { title: 'Reproduce el mapa 3D', text: 'Pulsa «Reproducir» para ver cambiar las barras fecha a fecha. Puedes pausar en cualquier momento y tocar una barra para ver los focos de esa zona.', target: 'fire-play-toggle' },
    { title: 'Salta a una fecha', text: 'Arrastra la línea de tiempo o toca la gráfica para ir a un periodo. Ajusta la altura de las barras si necesitas ver mejor las zonas con pocos focos.', target: 'fire-play-frame' },
    { title: 'Compara con lo habitual', text: 'En el selector del mapa puedes comparar un mes o la temporada de agosto a octubre con los años de referencia.', target: 'fire-map-layer' },
    { title: 'Revisa la semana guardada', text: 'El reporte compara los focos alrededor de cada lago con su promedio histórico. Mira la fecha y la etiqueta de simulacro cuando aparezca.', target: 'reporte-incendios' },
  ],
  vegetacion: [
    { title: 'Elige un lago y un indicador', text: 'Cada serie cuenta una parte del paisaje. Selecciona pérdida de bosque, superficie quemada, pasturas o cultivos y el área que quieres ver.', target: 'vegetation-series' },
    { title: 'Compara las imágenes', text: 'Las fotos muestran el paisaje en dos fechas. El mapa de cambios indica dónde aparecieron cambios de cobertura y cuántas hectáreas abarca cada tipo.', target: 'land-cover-images' },
  ],
  provincias: [
    { title: 'Elige una provincia', text: 'Toca el mapa o usa el selector. Verás su diagnóstico de largo plazo, la relación entre la lluvia y el verdor y los periodos de mayor déficit.', target: 'atlas-region' },
    { title: 'Reproduce los cambios', text: 'En «Qué quieres ver» elige sequía combinada, lluvia o verdor. El botón Reproducir recorre periodos de aproximadamente diez días.', target: 'atlas-layer' },
  ],
} as const;

export type GuideView = keyof typeof guides;

interface TourLayout {
  left: number; top: number; width: number; height: number; cardLeft: number; cardTop: number;
}

export function Guide({ view }: { view: GuideView }) {
  const [index, setIndex] = useState(0);
  const [open, setOpen] = useState(false);
  const [layout, setLayout] = useState<TourLayout>();
  const [resumeAt, setResumeAt] = useState<number>();
  const dialog = useRef<HTMLDialogElement>(null);
  const card = useRef<HTMLDivElement>(null);
  const steps = guides[view];
  const step = steps[index];
  const last = index === steps.length - 1;

  useEffect(() => {
    if (!open) return;
    let raf = 0;
    let current: HTMLElement | null = null;
    const resize = new ResizeObserver(() => position());
    if (card.current) resize.observe(card.current);
    function position() {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const target = document.getElementById(step.target);
        const bubble = card.current;
        if (!target || !bubble) return;
        if (target !== current) {
          if (current) resize.unobserve(current);
          current = target;
          resize.observe(target);
          target.scrollIntoView({ block: target.offsetHeight > window.innerHeight * .68 ? 'start' : 'center', behavior: 'instant' });
        }
        const rect = target.getBoundingClientRect();
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        const height = bubble.offsetHeight;
        const width = bubble.offsetWidth;
        const top = Math.max(rect.top - 7, 8);
        const bottom = Math.min(rect.bottom + 7, vh - 8);
        const left = Math.max(rect.left - 7, 8);
        const right = Math.min(rect.right + 7, vw - 8);
        const cardTop = bottom + height + 16 <= vh ? bottom + 12 : top - height - 12 >= 8 ? top - height - 12 : Math.max(8, vh - height - 12);
        const cardLeft = Math.max(9, Math.min(vw - width - 9, (left + right - width) / 2));
        setLayout({ left, top, width: Math.max(0, right - left), height: Math.max(0, bottom - top), cardLeft, cardTop });
      });
    }
    const observer = new MutationObserver(position);
    observer.observe(document.getElementById('contenido') ?? document.body, { childList: true, subtree: true });
    window.addEventListener('resize', position);
    window.addEventListener('scroll', position, { passive: true });
    position();
    return () => {
      observer.disconnect();
      resize.disconnect();
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', position);
      window.removeEventListener('scroll', position);
    };
  }, [open, step.target]);

  function changeStep(next: number) {
    setLayout(undefined);
    setIndex(next);
  }

  function tryControl() {
    const target = document.getElementById(step.target);
    if (!target) return;
    setResumeAt(last ? undefined : index + 1);
    dialog.current?.close();
    if (target.tabIndex < 0) target.tabIndex = -1;
    target.focus({ preventScroll: true });
  }

  return <>
    <button type="button" className="mission-guide-button" aria-haspopup="dialog" onClick={() => {
      changeStep(resumeAt ?? 0);
      setResumeAt(undefined);
      setOpen(true);
      dialog.current?.showModal();
    }}><CircleHelp size={21} aria-hidden="true" /> {resumeAt == null ? 'Guía' : 'Continuar guía'}</button>
    <dialog className="mission-guide mission-guide-tour" ref={dialog} aria-labelledby="mission-guide-title" onClose={() => setOpen(false)} onClick={(event) => {
      if (event.target === event.currentTarget) dialog.current?.close();
    }}>
      {layout ? <div className="guide-spotlight" aria-hidden="true" style={{ left: layout.left, top: layout.top, width: layout.width, height: layout.height }} />
        : <div className="guide-scrim" aria-hidden="true" />}
      <div className="guide-content guide-tour-card" ref={card} style={layout ? { left: layout.cardLeft, top: layout.cardTop } : undefined}>
        <div className="guide-heading"><p><Compass size={19} aria-hidden="true" /> Recorrido guiado</p>
          <button type="button" aria-label="Cerrar la guía" onClick={() => dialog.current?.close()}><X size={20} aria-hidden="true" /></button></div>
        <div aria-live="polite" aria-atomic="true">
          <p className="guide-progress">Paso {index + 1} de {steps.length}</p>
          <div className="guide-bars" aria-hidden="true">{steps.map((item, position) => <span key={item.title} className={position <= index ? 'complete' : undefined} />)}</div>
          <h2 id="mission-guide-title">{step.title}</h2>
          <p>{step.text}</p>
        </div>
        <button type="button" className="guide-jump" disabled={!layout} onClick={tryControl}>
          <ArrowDown size={16} aria-hidden="true" /> Probar este control</button>
        <div className="guide-actions">
          <button type="button" disabled={index === 0} onClick={() => changeStep(index - 1)}><ArrowLeft size={16} aria-hidden="true" /> Anterior</button>
          <button type="button" className="primary" onClick={() => last ? dialog.current?.close() : changeStep(index + 1)}>
            {last ? 'Terminar' : 'Siguiente'} {!last && <ArrowRight size={16} aria-hidden="true" />}
          </button>
        </div>
      </div>
    </dialog>
  </>;
}
