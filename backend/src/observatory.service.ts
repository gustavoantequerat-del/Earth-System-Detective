import { BadRequestException, Injectable, NotFoundException, ServiceUnavailableException } from '@nestjs/common';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { isAbsolute, join, resolve } from 'node:path';
import Database from 'better-sqlite3';
import { parse } from 'csv-parse/sync';
import { dataRoot } from './data-root';
import { isDrill, median, waterPriority, waterThreshold, type WatchSignal, type WeeklyRecord } from './watchlist';

interface Result {
  body_id: string;
  control_id?: string;
  name: string;
  lat: number;
  lon: number;
  state: string;
  confidence: string;
  years?: number[];
  baseline_end?: number;
  baseline_mean_ha?: number;
  trend: { change_pct: number };
}

interface Place { lat: number; lon: number }
interface ArchiveRow { body_id: string; [key: string]: string }
interface Context { years: [number, number]; window_km: number; changes_ha: Record<string, number> }
interface Verification { lagunas?: Record<string, unknown> }
const waterSignals = new Set(['natural_water_ha', 'artificial_water_ha', 'mining_water_ha', 'desaguadero_water_ha']);
const vegetationSignals = new Set(['forest_loss_ha', 'burned_ha', 'pasture_ha', 'agri_ha', 'dry_crop_ha',
  'mining_ha', 'urban_ha', 'night_lights', 'population', 'crop_water_hm3']);
const measurement = (value?: string) => value?.trim() && Number.isFinite(Number(value)) ? Number(value) : null;

export const reviewOutcomes = ['En revision', 'Confirmado en campo', 'Falso positivo', 'Requiere mas datos'];

@Injectable()
export class ObservatoryService {
  private readonly root = dataRoot();
  private readonly national = join(this.root, 'data', 'national');
  private readonly jsonCache = new Map<string, { mtime: number; size: number; value: unknown }>();
  private readonly csvCache = new Map<string, { mtime: number; size: number; records: ArchiveRow[] }>();

  private get data() {
    const configured = process.env.UMA_DATA;
    if (configured) return isAbsolute(configured) ? configured : resolve(this.root, configured);
    const real = join(this.root, 'data', 'real');
    return existsSync(join(real, 'results.json')) ? real : join(this.root, 'data', 'sample');
  }

  private json<T>(file: string, fallback: T): T {
    if (!existsSync(file)) return fallback;
    const { mtimeMs, size } = statSync(file);
    const previous = this.jsonCache.get(file);
    if (previous?.mtime === mtimeMs && previous.size === size) return previous.value as T;
    const contents = readFileSync(file, 'utf8').replace(/^\uFEFF/, '');
    // Older Python exports emitted non-finite literals for unavailable measurements.
    const validJson = contents.replace(/"(?:\\.|[^"\\])*"|-?Infinity|NaN/g, (token) => token.startsWith('"') ? token : 'null');
    const value: T = JSON.parse(validJson);
    this.jsonCache.set(file, { mtime: mtimeMs, size, value });
    return value;
  }

  private modelDir(method?: string, dir = this.data) {
    if (method === 'conservative') return join(dir, 'validation');
    if (!method || method === 'balance') return dir;
    throw new BadRequestException('Método de análisis desconocido.');
  }

  private csv(file: string): ArchiveRow[] {
    const path = join(this.data, file);
    if (!existsSync(path)) return [];
    const { mtimeMs, size } = statSync(path);
    const previous = this.csvCache.get(path);
    if (previous?.mtime === mtimeMs && previous.size === size) return previous.records;
    const records = parse(readFileSync(path), { columns: true, skip_empty_lines: true, bom: true }) as ArchiveRow[];
    this.csvCache.set(path, { mtime: mtimeMs, size, records });
    return records;
  }

  private results(dir = this.data) {
    const file = join(dir, 'results.json');
    if (!existsSync(file)) throw new ServiceUnavailableException('Los datos del observatorio no están disponibles en este despliegue.');
    return this.json<Result[]>(file, []);
  }

  private result(id: string, dir = this.data) {
    if (!/^[a-z0-9_]+$/i.test(id)) throw new NotFoundException('Cuerpo de agua no encontrado.');
    const result = this.results(dir).find((item) => item.body_id === id);
    if (!result) throw new NotFoundException('Cuerpo de agua no encontrado.');
    return result;
  }

  location(id: string) {
    if (!/^[a-z0-9_]+$/i.test(id)) throw new NotFoundException('Cuerpo de agua no encontrado.');
    const body = this.results().find((item) => item.body_id === id)
      ?? this.json<Result[]>(join(this.national, 'results.json'), []).find((item) => item.body_id === id);
    if (!body) throw new NotFoundException('Cuerpo de agua no encontrado.');
    return { id: body.body_id, lat: body.lat, lon: body.lon };
  }

  private measurements(id: string) {
    return this.csv('suspects.csv').flatMap((row) => {
      if (row.body_id !== id || !row.area) return [];
      const year = measurement(row.year);
      const value = measurement(row.value);
      return year != null && Number.isInteger(year) && value != null ? [{ area: row.area, year, suspect: row.suspect, value }] : [];
    });
  }

  private annualClimate(id: string) {
    return this.csv('series.csv').filter((row) => row.body_id === id).flatMap((row) => {
      const year = measurement(row.year);
      if (year == null || !Number.isInteger(year)) return [];
      return [{ year, waterHa: measurement(row.water_ha), jrcHa: measurement(row.water_ha_jrc), missingPct: measurement(row.nodata_pct),
        powerMm: measurement(row.precip_power_mm), chirpsMm: measurement(row.precip_chirps_mm),
        rainMm: measurement(row.precip_mm), tempC: measurement(row.temp_c), petMm: measurement(row.pet_mm),
        storageCm: measurement(row.groundwater_cm), oni: measurement(row.oni) }];
    }).sort((a, b) => a.year - b.year);
  }

  watchlist(method?: string) {
    const snapshot = this.dashboard(method);
    const report = this.json<WeeklyRecord | null>(join(this.data, 'alertas_semanales.json'), null);
    const weekly = report ? { date: report.week_end, drill: isDrill(report) } : null;
    const rules = { waterThreshold, waterPriority, vegetationPercent: 50, vegetationYears: 5, vegetationRatio: 1.5 } as const;
    if (snapshot.sample) return { signals: [], sample: true, weekly, rules };
    const signals: WatchSignal[] = snapshot.results.flatMap((body) => {
      const change = body.trend.change_pct;
      const period = body.years?.slice(-5);
      if (!Number.isFinite(change) || change > -waterThreshold || !period?.length) return [];
      return [{
        id: body.body_id, name: body.name, type: 'agua', level: change <= -waterPriority ? 'prioridad' : 'seguimiento',
        metric: change, reference: body.baseline_end ?? null, from: String(period[0]), to: String(period.at(-1)), state: body.state,
        source: 'Landsat · análisis de superficie',
      }];
    });

    for (const body of snapshot.results) {
      const loss = this.measurements(body.body_id).filter((row) => row.suspect === 'forest_loss_ha' && row.area === 'subcuenca_local')
        .sort((a, b) => a.year - b.year);
      const latest = loss.at(-1);
      if (!latest) continue;
      const previous = loss.filter(({ year }) => year >= latest.year - rules.vegetationYears && year < latest.year);
      if (previous.length !== rules.vegetationYears) continue;
      const usual = median(previous.map(({ value }) => value));
      if (usual > 0 && latest.value >= usual * rules.vegetationRatio) signals.push({
        id: body.body_id, name: body.name, type: 'vegetacion', level: 'seguimiento', metric: latest.value, reference: usual,
        from: String(previous[0].year), to: String(latest.year), source: 'Hansen Global Forest Change', area: latest.area,
      });
    }
    if (report && !isDrill(report)) {
      for (const body of report.rows) {
        if (!body.alerta) continue;
        for (const [area, counts] of Object.entries(body.areas)) {
          if (counts.alerta) signals.push({
            id: body.body_id, name: body.name, type: 'incendios', level: 'seguimiento', metric: counts.focos,
            reference: counts.normal, from: report.week_end, to: report.week_end, source: 'NASA FIRMS · reporte guardado', area,
          });
        }
      }
    }
    signals.sort((a, b) => Number(b.level === 'prioridad') - Number(a.level === 'prioridad')
      || Number(b.type === 'agua') - Number(a.type === 'agua')
      || (a.type === 'agua' ? a.metric - b.metric : b.to.localeCompare(a.to)));
    return { signals, sample: false, weekly, rules };
  }

  dashboard(method?: string) {
    const dir = this.data;
    return {
      results: this.results(this.modelDir(method, dir)),
      national: method === 'conservative' ? [] : this.json<Result[]>(join(this.national, 'results.json'), []),
      artificial: this.json(join(this.national, 'agua_artificial.json'), null),
      sample: dir === join(this.root, 'data', 'sample'),
      conservativeAvailable: existsSync(join(dir, 'validation', 'results.json')),
    };
  }

  places(id: string, dir = this.data) {
    this.result(id, dir);
    return this.json<Place[]>(join(dir, 'context', `${id}_lugares.json`), []);
  }

  detail(id: string, method?: string) {
    const dir = this.data;
    const result = this.result(id, this.modelDir(method, dir));
    const contextDir = join(dir, 'context');
    const context = ['antes', 'despues', 'cambios'].every((suffix) => existsSync(join(contextDir, `${id}_${suffix}.png`)))
      ? this.json<Context | null>(join(contextDir, `${id}_meta.json`), null)
      : null;
    const imagesDir = join(dir, 'img');
    const images = existsSync(imagesDir) ? new Set(readdirSync(imagesDir)) : new Set<string>();
    const imageYears = [...images].flatMap((filename) => {
      const match = filename.match(new RegExp(`^${id}_(\\d{4})\\.png$`));
      return match ? [{ year: Number(match[1]), mask: images.has(`${id}_${match[1]}_water.png`) }] : [];
    }).sort((a, b) => a.year - b.year);
    const signals = this.measurements(id);
    const water = signals.filter(({ suspect }) => waterSignals.has(suspect));
    const vegetation = signals.filter(({ suspect }) => vegetationSignals.has(suspect));
    const verification = this.json<Verification | null>(join(dir, 'verificacion.json'), null)?.lagunas?.[id] ?? null;
    const river = id === 'poopo' || id === 'uru_uru' || id === 'titicaca_menor'
      ? this.json(join(dir, 'desaguadero.json'), null)
      : null;
    const basin = this.csv('basins.csv').find((row) => row.body_id === id);
    const catchment = basin ? {
      areaKm2: measurement(basin.upstream_km2), subbasins: measurement(basin.n_subbasins),
      upstream: basin.upstream_bodies?.split(',').map((id) => id.trim()).filter(Boolean) ?? [],
    } : null;
    return { result, context, imageYears, places: this.places(id, dir), water, vegetation, verification, river,
      climate: this.annualClimate(id), catchment };
  }

  image(folder: string, filename: string) {
    if ((folder !== 'context' && folder !== 'img') || !/^[a-z0-9_]+\.png$/i.test(filename)) {
      throw new NotFoundException('Imagen no encontrada.');
    }
    const file = join(this.data, folder, filename);
    if (!existsSync(file)) throw new NotFoundException('Imagen no encontrada.');
    return readFileSync(file);
  }

  download(method?: string) {
    return Buffer.from(JSON.stringify(this.results(this.modelDir(method)), null, 2));
  }

  private withDb<T>(callback: (db: Database.Database) => T, fallback: T, write = false, dir = this.data) {
    const file = join(dir, 'uma.db');
    if (!existsSync(file)) return fallback;
    const db = new Database(file, { readonly: !write, fileMustExist: true });
    try {
      return callback(db);
    } finally {
      db.close();
    }
  }

  history(id: string, method?: string) {
    const dir = this.modelDir(method);
    this.result(id, dir);
    return this.withDb((db) => ({
      available: true,
      canReview: process.env.VERCEL !== '1',
      runs: db.prepare(`
        SELECT r.run_id AS corrida, r.created_at AS fecha, v.state AS estado, v.confidence AS confianza,
          v.n_pass AS pruebas, ROUND(v.change_pct) AS cambio_pct, v.control_id AS gemela,
          r.note AS nota, r.inputs_sha256 AS huella_datos, r.code_sha256 AS huella_codigo
        FROM verdicts v JOIN runs r USING(run_id) WHERE v.body_id = ? ORDER BY r.run_id DESC
      `).all(id),
      reviews: db.prepare(`
        SELECT created_at AS fecha, reviewer AS revisor, outcome AS resultado, comment AS comentario
        FROM reviews WHERE body_id = ? ORDER BY review_id DESC
      `).all(id),
      alerts: db.prepare(`
        SELECT state AS estado, opened_at AS abierta, closed_at AS cerrada, status AS situacion
        FROM alerts WHERE body_id = ? ORDER BY alert_id DESC
      `).all(id),
    }), { available: false, canReview: false, runs: [], reviews: [], alerts: [] }, false, dir);
  }

  review(id: string, body: Record<string, unknown> | undefined, method?: string) {
    if (process.env.VERCEL === '1') {
      throw new ServiceUnavailableException('Las revisiones requieren una base de datos persistente.');
    }
    const dir = this.modelDir(method);
    this.result(id, dir);
    const { reviewer, outcome, comment = '' } = body ?? {};
    if (typeof reviewer !== 'string' || !reviewer.trim() || reviewer.length > 200 ||
        typeof outcome !== 'string' || !reviewOutcomes.includes(outcome) ||
        typeof comment !== 'string' || comment.length > 5000) {
      throw new BadRequestException('Completa el nombre y el resultado de la revisión.');
    }
    const saved = this.withDb((db) => {
      db.prepare(`
        INSERT INTO reviews (body_id, run_id, created_at, reviewer, outcome, comment)
        VALUES (?, (SELECT MAX(run_id) FROM runs), ?, ?, ?, ?)
      `).run(id, new Date().toISOString(), reviewer.trim(), outcome, comment.trim());
      return true;
    }, false, true, dir);
    if (!saved) throw new NotFoundException('No hay una base de auditoría para estos datos.');
    return { saved };
  }

  fireMap() {
    const archive = this.json(join(this.root, 'data', 'real', 'fires-map.json'), null);
    if (!archive) throw new NotFoundException('El archivo histórico de focos MODIS no está disponible.');
    return archive;
  }

  weekly() {
    const report = this.json(join(this.data, 'alertas_semanales.json'), null);
    const history = this.withDb((db) => {
      const table = db.prepare("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'operational_alerts'").get();
      return table ? db.prepare(`
        SELECT week_end AS semana, body_id, area, fires AS focos, normal, alert AS alerta, notified AS aviso
        FROM operational_alerts ORDER BY week_end DESC
      `).all() : [];
    }, []);
    return { report, history };
  }
}
