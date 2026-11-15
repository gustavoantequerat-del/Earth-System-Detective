import { Injectable, NotFoundException, ServiceUnavailableException } from '@nestjs/common';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { gunzipSync } from 'node:zlib';
import { dataRoot } from './data-root';

interface RegionalArchive {
  origin: string;
  verdicts: { pcode: string; name: string; adm1_name: string; level: string; verdict: string; n_pixels: number }[];
  analyses: Record<string, object>;
  timeline: {
    dates: string[];
    regions: Record<string, { name: string; adm1_name: string; r3q: (number | null)[]; viq: (number | null)[] }>;
  };
}

@Injectable()
export class RegionalVegetationService {
  private readonly root = dataRoot();
  private stored?: RegionalArchive;
  private geometry?: object;

  private get archive() {
    if (!this.stored) {
      const file = join(this.root, 'data', 'real', 'vegetation-regions.json.gz');
      if (!existsSync(file)) throw new ServiceUnavailableException('El archivo provincial no está disponible en este despliegue.');
      this.stored = JSON.parse(gunzipSync(readFileSync(file)).toString('utf8')) as RegionalArchive;
    }
    return this.stored;
  }

  regions() {
    if (!this.geometry) {
      const file = join(this.root, 'Naseros', 'data', 'bol_admin2_simplified.geojson.gz');
      if (!existsSync(file)) throw new ServiceUnavailableException('No están disponibles los límites provinciales.');
      this.geometry = JSON.parse(gunzipSync(readFileSync(file)).toString('utf8')) as object;
    }
    const { origin, verdicts, timeline } = this.archive;
    return { origin, verdicts, geometry: this.geometry, from: timeline.dates[0], to: timeline.dates.at(-1) };
  }

  timeline() { return this.archive.timeline; }

  analysis(code: string) {
    const id = code.toUpperCase();
    if (!/^BO\d{4}$/.test(id) || !Object.hasOwn(this.archive.analyses, id)) {
      throw new NotFoundException('La provincia no tiene datos suficientes para el análisis.');
    }
    return this.archive.analyses[id];
  }
}
