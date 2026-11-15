import { Injectable, Logger, ServiceUnavailableException } from '@nestjs/common';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { PNG } from 'pngjs';
import { dataRoot } from './data-root';

// The official npm client generates its image and geometry methods at initialization.
const ee = require('@google/earthengine');
const waterAsset = 'projects/mapbiomas-public/assets/bolivia/water/collection4/mapbiomas_bolivia_collection4_water_bodies_v1';
const terrainTiles = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium';
const landsatSensors = [
  { id: 'LT05', start: 1985, end: 2012, rgb: ['SR_B3', 'SR_B2', 'SR_B1'] },
  { id: 'LE07', start: 2011, end: 2013, rgb: ['SR_B3', 'SR_B2', 'SR_B1'] },
  { id: 'LC08', start: 2013, end: 2024, rgb: ['SR_B4', 'SR_B3', 'SR_B2'] },
  { id: 'LC09', start: 2013, end: 2024, rgb: ['SR_B4', 'SR_B3', 'SR_B2'] },
];

@Injectable()
export class MapService {
  private readonly logger = new Logger(MapService.name);
  private initialization?: Promise<void>;
  private readonly textures = new Map<string, { request: Promise<string>; expires: number }>();
  private readonly climate = new Map<string, { request: Promise<Record<string, number | null>>; expires: number }>();
  private readonly terrain = new Map<string, Promise<PNG>>();

  get configured() {
    return Boolean(process.env.GEE_SERVICE_ACCOUNT_KEY || process.env.GOOGLE_APPLICATION_CREDENTIALS);
  }

  private async initialize() {
    if (!this.initialization) {
      this.initialization = this.authenticate().catch((error) => {
        this.initialization = undefined;
        throw error;
      });
    }
    return this.initialization;
  }

  private async authenticate() {
    const root = resolve(__dirname, '../../');
    const credentials = process.env.GOOGLE_APPLICATION_CREDENTIALS;
    const key = JSON.parse(process.env.GEE_SERVICE_ACCOUNT_KEY || readFileSync(resolve(root, credentials ?? ''), 'utf8'));
    const settings = resolve(dataRoot(), 'config', 'settings.json');
    const project = process.env.UMA_GEE_PROJECT ||
      (existsSync(settings) ? JSON.parse(readFileSync(settings, 'utf8')).gee_project : undefined) ||
      key.project_id;
    await new Promise<void>((success, failure) => ee.data.authenticateViaPrivateKey(key, success, failure));
    await new Promise<void>((success, failure) => ee.initialize(null, null, success, failure, null, project));
  }

  compareClimate(point: { lat: number; lon: number }, month: string) {
    const base = { radiusKm: 20, month, sources: ['NASA GPM IMERG V07', 'CHIRPS', 'ERA5-Land'] };
    if (!this.configured) return Promise.resolve({ ...base, status: 'not_configured', values: null });
    const cacheKey = `${point.lat},${point.lon},${month}`;
    const cached = this.climate.get(cacheKey);
    if (cached && cached.expires > Date.now()) {
      return cached.request.then((values) => ({ ...base, status: 'available', values }))
        .catch(() => ({ ...base, status: 'unavailable', values: null }));
    }
    const request = this.climateForMonth(point, month);
    const entry = { request, expires: Date.now() + 60 * 60 * 1000 };
    if (this.climate.size >= 48) this.climate.delete(this.climate.keys().next().value!);
    this.climate.set(cacheKey, entry);
    return request.then((values) => ({ ...base, status: 'available', values })).catch(() => {
      entry.expires = Date.now() + 30_000;
      return { ...base, status: 'unavailable', values: null };
    });
  }

  private async climateForMonth(point: { lat: number; lon: number }, month: string) {
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      return await Promise.race([new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error('Earth Engine no respondió a tiempo')), 10000);
      }), (async () => {
        await this.initialize();
        const start = ee.Date(month + '-01');
        const end = start.advance(1, 'month');
        const region = ee.Geometry.Point([point.lon, point.lat]).buffer(20000);
        const select = (id: string, field: string) => ee.ImageCollection(id).filterDate(start, end).select(field);
        const imerg = select('NASA/GPM_L3/IMERG_MONTHLY_V07', 'precipitation');
        const chirps = select('UCSB-CHG/CHIRPS/DAILY', 'precipitation');
        const eraRain = select('ECMWF/ERA5_LAND/MONTHLY_AGGR', 'total_precipitation_sum');
        const eraTemp = select('ECMWF/ERA5_LAND/MONTHLY_AGGR', 'temperature_2m');
        const days = end.difference(start, 'day');
        const mean = (image: ReturnType<typeof ee.Image>, band: string, scale: number) => image.reduceRegion({
          reducer: ee.Reducer.mean(), geometry: region, scale, maxPixels: 10000,
        }).get(band);
        const values = ee.Dictionary({
          gpmMm: ee.Algorithms.If(imerg.size().gt(0), mean(imerg.mean().multiply(days.multiply(24)), 'precipitation', 11132), null),
          chirpsMm: ee.Algorithms.If(chirps.size().eq(days), mean(chirps.sum(), 'precipitation', 5566), null),
          eraRainMm: ee.Algorithms.If(eraRain.size().gt(0), mean(eraRain.mean().multiply(1000), 'total_precipitation_sum', 11132), null),
          eraTempC: ee.Algorithms.If(eraTemp.size().gt(0), mean(eraTemp.mean().subtract(273.15), 'temperature_2m', 11132), null),
        });
        return new Promise<Record<string, number | null>>((resolve, reject) => values.evaluate(
          (result: Record<string, number | null> | undefined, error: string | undefined) => result ? resolve(result) : reject(new Error(error)),
        ));
      })()]);
    } finally { if (timer) clearTimeout(timer); }
  }

  async texture(mode: 'water' | 'landsat', year: number, fires: boolean) {
    if (!this.configured) throw new ServiceUnavailableException('Configura la cuenta de servicio de Earth Engine.');
    const day = new Date().toISOString().slice(0, 10);
    const key = `${mode}:${year}:${fires ? day : ''}`;
    const cached = this.textures.get(key);
    if (cached && cached.expires > Date.now()) return cached.request;
    const request = this.createTexture(mode, year, fires, day).catch((error: unknown) => {
      this.textures.delete(key);
      const message = error instanceof Error ? error.message : String(error);
      this.logger.warn(`Earth Engine: ${message}`);
      throw new ServiceUnavailableException('No se pudo cargar la capa de Earth Engine.');
    });
    if (this.textures.size >= 64) this.textures.delete(this.textures.keys().next().value!);
    this.textures.set(key, { request, expires: Date.now() + 30 * 60 * 1000 });
    return request;
  }

  private landsat(year: number, region: unknown) {
    const collections = landsatSensors.filter(({ start, end }) => year >= start && year <= end)
      .map(({ id, rgb }) => ee.ImageCollection(`LANDSAT/${id}/C02/T1_L2`)
        .filterDate(`${year}-06-01`, `${year}-10-31`).filterBounds(region)
        .map((image: ReturnType<typeof ee.Image>) => {
          const qa = image.select('QA_PIXEL');
          const clear = qa.bitwiseAnd(1 << 3).eq(0).and(qa.bitwiseAnd(1 << 4).eq(0));
          return image.select(rgb, ['R', 'G', 'B']).multiply(0.0000275).add(-0.2).updateMask(clear);
        }));
    const mosaic = collections.reduce((merged, collection) => merged.merge(collection)).median();
    return mosaic.select(['R', 'G', 'B']).visualize({ min: 0, max: 0.25, gamma: 1.3 });
  }

  private async createTexture(mode: 'water' | 'landsat', year: number, fires: boolean, day: string) {
    await this.initialize();
    const bounds = ee.Geometry.Rectangle([-70.5, -23.5, -57.0, -9.5]);
    const base = mode === 'water'
      ? ee.Terrain.hillshade(ee.Image('NASA/NASADEM_HGT/001').select('elevation')).visualize({
        min: 60, max: 255, palette: ['1b1f24', '8a929c'],
      })
      : this.landsat(Math.min(year, 2024), bounds);
    const classes = ee.Image(waterAsset).select(`classification_${year}`);
    const natural = classes.gte(11).and(classes.lte(14)).selfMask().visualize({ palette: ['0d2f8a'], opacity: 0.95 });
    const artificial = classes.gte(21).and(classes.lte(24)).selfMask().visualize({ palette: ['00f5ff'] });
    const country = ee.FeatureCollection('FAO/GAUL/2015/level0')
      .filter(ee.Filter.eq('ADM0_NAME', 'Bolivia')).geometry().simplify(2000).buffer(15000);
    let image = base.blend(natural).blend(artificial).clip(country);
    if (fires) {
      const date = ee.Date(day);
      const heat = ee.ImageCollection('FIRMS').filterDate(date.advance(-7, 'day'), date.advance(1, 'day'))
        .select('T21').max().gt(0).selfMask().focalMax(2);
      image = image.blend(heat.visualize({ palette: ['ff3d00'] }));
    }
    return new Promise<string>((success, failure) => {
      image.getMap({}, (map?: { urlFormat: string }, error?: string) => {
        if (map?.urlFormat) success(map.urlFormat);
        else failure(new Error(error ?? 'La respuesta no incluyó teselas.'));
      });
    });
  }

  async elevations(points: { lat: number; lon: number }[]) {
    return Promise.all(points.map(async (point) => {
      const z = 10;
      const scale = 2 ** z;
      const longitude = (point.lon + 180) / 360 * scale;
      const latitude = (1 - Math.asinh(Math.tan(point.lat * Math.PI / 180)) / Math.PI) / 2 * scale;
      const x = Math.floor(longitude);
      const y = Math.floor(latitude);
      try {
        const tile = await this.terrainTile(`${z}/${x}/${y}`);
        const offset = (Math.floor((latitude - y) * tile.height) * tile.width +
          Math.floor((longitude - x) * tile.width)) * 4;
        const elevation = tile.data[offset] * 256 + tile.data[offset + 1] + tile.data[offset + 2] / 256 - 32768;
        return { lat: point.lat, lon: point.lon, elevation };
      } catch {
        return { lat: point.lat, lon: point.lon, elevation: null };
      }
    }));
  }

  private terrainTile(key: string) {
    const cached = this.terrain.get(key);
    if (cached) return cached;
    const request = fetch(`${terrainTiles}/${key}.png`, { signal: AbortSignal.timeout(4000) })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Terrain tile ${response.status}`);
        return PNG.sync.read(Buffer.from(await response.arrayBuffer()));
      }).catch((error: unknown) => {
        this.terrain.delete(key);
        throw error;
      });
    if (this.terrain.size >= 96) this.terrain.delete(this.terrain.keys().next().value!);
    this.terrain.set(key, request);
    return request;
  }
}
