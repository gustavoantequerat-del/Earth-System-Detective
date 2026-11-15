'use client';

import { useState } from 'react';
import { Droplet, Search, X } from 'lucide-react';
import { searchKey, waterChange, type WaterBody } from './data';
import { Status } from './ui';

export function LakeSearch({ id, bodies, onSelect }: { id: string; bodies: WaterBody[]; onSelect: (id: string) => void }) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const key = searchKey(query);
  const matches = key ? bodies.map((body) => ({ body, name: searchKey(body.name) }))
    .filter(({ name }) => name.includes(key))
    .sort((a, b) => Number(b.name.startsWith(key)) - Number(a.name.startsWith(key)) || a.name.localeCompare(b.name, 'es'))
    .map(({ body }) => body) : bodies;

  function choose(body: WaterBody) {
    setQuery(body.name);
    setOpen(false);
    onSelect(body.body_id);
  }

  return <div className="lake-search" onBlur={(event) => {
    if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
  }} onKeyDown={(event) => {
    if (event.key === 'Escape' && open) {
      event.stopPropagation();
      document.getElementById(id)?.focus();
      setOpen(false);
    }
  }}>
    <label htmlFor={id}>Buscar un lago o una laguna</label>
    <div className="lake-search-field">
      <Search size={19} aria-hidden="true" />
      <input id={id} type="search" placeholder="Ej. Poopó o Titicaca" value={query} autoComplete="off"
        aria-describedby={id + '-hint'} aria-controls={open ? id + '-matches' : undefined}
        onFocus={() => setOpen(true)} onChange={(event) => { setQuery(event.target.value); setOpen(true); }}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && open && matches[0]) {
            event.preventDefault();
            choose(matches[0]);
          }
          if (event.key === 'ArrowDown' && open && matches.length) {
            event.preventDefault();
            document.getElementById(id + '-matches')?.querySelector('button')?.focus();
          }
        }} />
      {query && <button aria-label="Limpiar búsqueda" type="button" onClick={() => {
        setQuery('');
        document.getElementById(id)?.focus();
        setOpen(true);
      }}><X size={16} aria-hidden="true" /></button>}
    </div>
    <p id={id + '-hint'} className="lake-search-hint">Escribe el nombre y elige uno de los resultados.</p>
    {open && <div id={id + '-matches'} className="lake-search-results">
      <p role="status">{key ? (matches.length ? `${matches.length} ${matches.length === 1 ? 'resultado' : 'resultados'}`
        : 'No encontramos ese nombre. Prueba con una parte del nombre.') : 'Lagos y lagunas para explorar'}</p>
      {!!matches.length && <ul aria-label="Resultados de búsqueda">
        {matches.slice(0, 10).map((body) => <li key={body.body_id}><button type="button" onClick={() => choose(body)}>
          <span className="lake-result-icon"><Droplet size={17} aria-hidden="true" /></span>
          <span><strong>{body.name}</strong><small>{waterChange(body.trend.change_pct)}</small></span>
          <Status state={body.state} />
        </button></li>)}
      </ul>}
      {matches.length > 10 && <p>Mostramos los primeros 10. Escribe un nombre más específico para acotar.</p>}
    </div>}
  </div>;
}
