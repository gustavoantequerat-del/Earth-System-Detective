'use client';

import { useMemo, useState } from 'react';
import DeckGL from '@deck.gl/react';
import type { PickingInfo } from '@deck.gl/core';
import { TileLayer } from '@deck.gl/geo-layers';
import { BitmapLayer, PathLayer, ScatterplotLayer, TextLayer } from '@deck.gl/layers';
import { number, type OsmKind, type RiverSummary } from './data';
import { escapeHtml, kindColors, waterTone } from './rivers-palette';

const esri = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
const view = { longitude: -67.95, latitude: -17.75, zoom: 7.1, pitch: 0, bearing: 0 };
const lakes = [
  { name: 'Lago Titicaca (Menor)', position: [-68.85, -16.4] as [number, number] },
  { name: 'Uru Uru', position: [-67.12, -18.07] as [number, number] },
  { name: 'Poopó', position: [-67.05, -18.85] as [number, number] },
];

type Path = { reach: string; name: string; path: [number, number][]; color: [number, number, number]; pct: number | null; selected: boolean };
type Point = RiverSummary['osm_points'][number];

export default function RiversMap({ data, lakeReaches, selected, onSelect, kinds }: {
  data: RiverSummary; lakeReaches: string[]; selected: string | null; onSelect: (reach: string) => void; kinds: Set<OsmKind>;
}) {
  const [hover, setHover] = useState<{ x: number; y: number; html: string } | null>(null);
  const byId = useMemo(() => new Map(data.reaches.map((reach) => [reach.id, reach])), [data]);
  const paths: Path[] = data.geometry.filter((feature) => lakeReaches.includes(feature.reach)).flatMap((feature) => {
    const pct = byId.get(feature.reach)?.water.pct ?? null;
    return feature.paths.map((path) => ({ reach: feature.reach, name: feature.name, path, pct,
      color: waterTone(pct).rgb, selected: feature.reach === selected }));
  });
  const points = data.osm_points.filter((point) => point.kind !== 'Otro' && kinds.has(point.kind as OsmKind) &&
    ((point.reach && lakeReaches.includes(point.reach)) || point.lake));

  const layers = [
    new TileLayer({
      id: 'imagery', data: esri, minZoom: 0, maxZoom: 17, tileSize: 256,
      renderSubLayers: (props) => {
        const [[west, south], [east, north]] = (props.tile as unknown as { boundingBox: [[number, number], [number, number]] }).boundingBox;
        return new BitmapLayer({ ...props, data: undefined, image: props.data as string, bounds: [west, south, east, north],
          desaturate: 0.35, tintColor: [210, 225, 230] });
      },
    }),
    new PathLayer<Path>({
      id: 'reaches-glow', data: paths, getPath: (d) => d.path, getColor: [8, 20, 24, 200],
      getWidth: (d) => d.selected ? 14 : 9, widthUnits: 'pixels', capRounded: true, jointRounded: true,
      updateTriggers: { getWidth: selected },
    }),
    new PathLayer<Path>({
      id: 'reaches', data: paths, getPath: (d) => d.path, getColor: (d) => d.color,
      getWidth: (d) => d.selected ? 9 : 5, widthUnits: 'pixels', capRounded: true, jointRounded: true, pickable: true,
      updateTriggers: { getWidth: selected },
      onClick: ({ object }) => { if (object) onSelect(object.reach); },
    }),
    new ScatterplotLayer<Point>({
      id: 'osm', data: points, getPosition: (d) => [d.lon, d.lat], getRadius: 450, radiusMinPixels: 3, radiusMaxPixels: 9,
      getFillColor: (d) => kindColors[d.kind as OsmKind].rgb, stroked: true, getLineColor: [255, 255, 255, 200],
      lineWidthMinPixels: 1, pickable: true,
    }),
    new TextLayer({
      id: 'lakes', data: lakes, getPosition: (d) => d.position, getText: (d) => d.name, getSize: 13,
      getColor: [240, 250, 252], outlineWidth: 3, outlineColor: [6, 22, 26, 230], fontSettings: { sdf: true },
      fontWeight: 700, getTextAnchor: 'middle', getAlignmentBaseline: 'center',
    }),
  ];

  function tooltip(info: PickingInfo) {
    const object = info.object as Path | Point | undefined;
    if (!object) return setHover(null);
    const html = 'path' in object
      ? `<b>${object.reach} · ${escapeHtml(object.name)}</b><br/>Agua en el cauce: ${object.pct == null ? 'sin dato' : `${object.pct > 0 ? '+' : ''}${number(object.pct)} %`}<br/><small>Clic para ver el tramo</small>`
      : `<b>${escapeHtml(object.name || object.kind)}</b><br/>${escapeHtml(object.kind)}${object.dist_river_km != null ? ` · a ${number(object.dist_river_km, 1)} km del río` : ''}`;
    setHover({ x: info.x, y: info.y, html });
  }

  return <div className="rivers-map" onMouseLeave={() => setHover(null)}>
    <DeckGL initialViewState={view} controller={{ dragRotate: false }} layers={layers} onHover={tooltip}
      getCursor={({ isHovering }) => isHovering ? 'pointer' : 'grab'} />
    {hover && <div className="rivers-map-tip" style={{ left: hover.x, top: hover.y }} dangerouslySetInnerHTML={{ __html: hover.html }} />}
    <span className="attribution">Imagen: Esri World Imagery · Cauce: HydroSHEDS · Obras: © OpenStreetMap</span>
  </div>;
}
