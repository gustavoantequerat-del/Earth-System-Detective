import { Injectable } from '@nestjs/common';
import { parse } from 'csv-parse/sync';

type Point = { lat: number; lon: number };
type Station = Point & { body_id: string; name: string };
type DataState = 'available' | 'empty' | 'unavailable' | 'not_configured';
const reference = [1991, 2020] as const;
const powerSource = 'NASA POWER · MERRA-2';
const firmsSource = 'NASA FIRMS · VIIRS NOAA-20';
const firmsDays = 3;
const radiusKm = 25;
const cmr = 'https://cmr.earthdata.nasa.gov/search/granules.json';
const collections = [
  { id: 'C2021957657-LPCLOUD', name: 'HLS Landsat', purpose: 'Escenas de reflectancia terrestre' },
  { id: 'C2021957295-LPCLOUD', name: 'HLS Sentinel-2', purpose: 'Escenas de reflectancia terrestre' },
  { id: 'C2617126679-POCLOUD', name: 'OPERA DSWx', purpose: 'Mapas satelitales de extensión de agua' },
  { id: 'C2799438230-POCLOUD', name: 'SWOT LakeSP', purpose: 'Archivos con medidas de lagos' },
  { id: 'C2723754851-GES_DISC', name: 'GPM IMERG Final', purpose: 'Producto mensual de precipitación' },
] as const;
const additionalCollections = [
  { id: 'C1748066515-LPCLOUD', name: 'MODIS Terra', purpose: 'Índices de vegetación (NDVI y EVI)' },
  { id: 'C2307290656-LPCLOUD', name: 'MODIS Aqua', purpose: 'Índices de vegetación (NDVI y EVI)' },
  { id: 'C3860065683-LAADS', name: 'VIIRS Black Marble', purpose: 'Luces nocturnas anuales' },
  { id: 'C1701805681-GES_DISC', name: 'AIRS · Aqua', purpose: 'Temperatura y humedad de la atmósfera' },
  { id: 'C3333493715-GES_DISC', name: 'OMI · Aura', purpose: 'Dióxido de nitrógeno atmosférico (NO₂)' },
  { id: 'C2938664763-NSIDC_CPRD', name: 'SMAP', purpose: 'Humedad superficial del suelo a escala regional' },
  { id: 'C1342986036-GES_DISC', name: 'GLDAS Noah', purpose: 'Humedad del suelo, escorrentía y otras variables modeladas' },
  { id: 'C1276812868-GES_DISC', name: 'MERRA-2', purpose: 'Flujos de superficie del reanálisis climático' },
] as const;

interface PowerPayload {
  header?: { fill_value?: number };
  parameters?: Record<string, { units: string }>;
  properties?: { parameter?: Record<string, Record<string, number>> };
}

interface CmrGranule { id: string; title: string; time_start?: string; cloud_cover?: string }
interface FirmDetection { latitude: string; longitude: string; acq_date: string; acq_time?: string; confidence?: string; frp?: string }

const readable = (r: Response) => {
  if (!r.ok) throw new Error('Proveedor no disponible');
  return r;
};

function average(values: number[]) {
  return values.length ? values.reduce((total, value) => total + value, 0) / values.length : null;
}

function separation(a: Point, b: Point) {
  const rad = Math.PI / 180;
  const haversine = Math.sin((a.lat - b.lat) * rad / 2) ** 2
    + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin((a.lon - b.lon) * rad / 2) ** 2;
  return 12742 * Math.asin(Math.sqrt(Math.min(1, haversine)));
}

@Injectable()
export class NasaService {
  private readonly cache = new Map<string, { expires: number; promise: Promise<unknown> }>();

  private cached<T>(key: string, minutes: number, load: () => Promise<T>): Promise<T> {
    const previous = this.cache.get(key);
    if (previous && previous.expires > Date.now()) return previous.promise as Promise<T>;
    if (this.cache.size >= 64) this.cache.delete(this.cache.keys().next().value!);
    const entry: { expires: number; promise: Promise<T> } = { expires: Date.now() + minutes * 60_000, promise: load() };
    this.cache.set(key, entry);
    entry.promise.catch(() => { entry.expires = Date.now() + 30_000; });
    return entry.promise;
  }

  async power(point: Point) {
    const now = new Date();
    const currentMonth = now.toISOString().slice(0, 7).replace('-', '');
    const url = new URL('https://power.larc.nasa.gov/api/temporal/monthly/point');
    url.search = new URLSearchParams({ parameters: 'PRECTOTCORR,T2M', community: 'AG', format: 'JSON',
      latitude: point.lat.toFixed(3), longitude: point.lon.toFixed(3), start: String(reference[0]), end: String(now.getUTCFullYear()) }).toString();
    const fallback = { status: 'unavailable' as DataState, source: powerSource, reference, months: [] };
    try {
      return await this.cached(url.href, 360, async () => {
        const data: PowerPayload = await fetch(url, { signal: AbortSignal.timeout(8000) }).then(readable).then((r) => r.json());
        const rain = data.properties?.parameter?.PRECTOTCORR;
        const temp = data.properties?.parameter?.T2M;
        if (!rain || !temp || data.parameters?.PRECTOTCORR?.units !== 'mm/day') throw new Error('Respuesta POWER inesperada');
        const valid = (value?: number) => Number.isFinite(value) && value !== (data.header?.fill_value ?? -999) ? value! : null;
        const rows = [...new Set([...Object.keys(rain), ...Object.keys(temp)])].filter((key) => /^\d{4}(0[1-9]|1[0-2])$/.test(key))
          .sort().filter((key) => key < currentMonth).map((key) => {
            const year = Number(key.slice(0, 4));
            const month = Number(key.slice(4));
            const daily = valid(rain[key]);
            return { year, month, date: `${key.slice(0, 4)}-${key.slice(4)}`,
              rainMm: daily == null || daily < 0 ? null : daily * new Date(Date.UTC(year, month, 0)).getUTCDate(),
              tempC: valid(temp[key]) };
          });
        const climatology = rows.filter(({ year }) => year >= reference[0] && year <= reference[1]);
        const months = rows.filter((row) => row.rainMm != null || row.tempC != null).slice(-6).map(({ month, date, rainMm, tempC }) => {
          const sameMonth = climatology.filter((row) => row.month === month);
          const rainNormalMm = average(sameMonth.flatMap((item) => item.rainMm == null ? [] : [item.rainMm]));
          const tempNormalC = average(sameMonth.flatMap((item) => item.tempC == null ? [] : [item.tempC]));
          return { date, rainMm, tempC, rainNormalMm, tempNormalC };
        });
        return { status: (months.length ? 'available' : 'empty') as DataState, source: powerSource, reference, months };
      });
    } catch { return fallback; }
  }

  async granules(point: Point, additional = false) {
    const boundingBox = [point.lon - .25, point.lat - .25, point.lon + .25, point.lat + .25].map((value) => value.toFixed(3)).join(',');
    return Promise.all((additional ? additionalCollections : collections).map(async (collection) => {
      const { id, name, purpose } = collection;
      const url = new URL(cmr);
      url.search = new URLSearchParams({ collection_concept_id: id, bounding_box: boundingBox, page_size: '1', 'sort_key[]': '-start_date' }).toString();
      const query = new URLSearchParams({ 'p': id, sb: boundingBox });
      const earthdata = 'https://search.earthdata.nasa.gov/search/granules?' + query.toString();
      const base = { id, name, purpose, earthdata };
      try {
        return await this.cached(url.href, 360, async () => {
          const result: { feed?: { entry?: CmrGranule[] } } = await fetch(url, { signal: AbortSignal.timeout(7000) }).then(readable).then((r) => r.json());
          if (!Array.isArray(result.feed?.entry)) throw new Error('Respuesta CMR inesperada');
          const entry = result.feed.entry[0];
          const cloud = entry?.cloud_cover?.trim() ? Number(entry.cloud_cover) : NaN;
          return { ...base, status: (entry ? 'available' : 'empty') as DataState, granule: entry ? {
            date: entry.time_start?.slice(0, 10), title: entry.title, cloudPct: Number.isFinite(cloud) ? cloud : null,
          } : null };
        });
      } catch {
        return { ...base, status: 'unavailable' as DataState, granule: null };
      }
    }));
  }

  async fires(bodies: Station[]) {
    const base = { source: firmsSource, days: firmsDays, radiusKm, lastDetection: null, lakes: [] };
    const key = process.env.FIRMS_MAP_KEY?.trim();
    if (!key) return { ...base, status: 'not_configured' as DataState };
    try {
      const data = await this.cached('firms-bolivia', 20, async () => {
        const url = `https://firms.modaps.eosdis.nasa.gov/api/area/csv/${encodeURIComponent(key)}/VIIRS_NOAA20_NRT/-70.1,-23.2,-57.4,-9.5/${firmsDays}`;
        const csv = await fetch(url, { signal: AbortSignal.timeout(8000) }).then(readable).then((r) => r.text());
        if (!/^latitude,longitude,/i.test(csv.trimStart())) throw new Error('Respuesta FIRMS inesperada');
        const rows = parse(csv, { columns: true, skip_empty_lines: true, bom: true }) as FirmDetection[];
        return rows.filter((row) => row.confidence !== 'l' && /^\d{4}-\d{2}-\d{2}$/.test(row.acq_date))
          .map((row) => ({ lat: Number(row.latitude), lon: Number(row.longitude), date: row.acq_date }))
          .filter((row) => Number.isFinite(row.lat) && Number.isFinite(row.lon));
      });
      const lakes = bodies.map((body) => {
        const near = data.filter((point) => separation(point, body) <= radiusKm);
        const lastDetection = near.reduce((latest, point) => point.date > latest ? point.date : latest, '');
        return { id: body.body_id, name: body.name, count: near.length, lastDetection: lastDetection || null };
      }).sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
      return { ...base, status: 'available' as DataState, lakes,
        lastDetection: data.reduce((latest, point) => point.date > latest ? point.date : latest, '') || null };
    } catch { return { ...base, status: 'unavailable' as DataState }; }
  }
}
