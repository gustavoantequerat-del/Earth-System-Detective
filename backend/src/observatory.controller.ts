import { BadRequestException, Body, Controller, Get, Header, Param, Post, Query, StreamableFile } from '@nestjs/common';
import { ObservatoryService } from './observatory.service';
import { MapService } from './map.service';
import { NasaService } from './nasa.service';
import { RegionalVegetationService } from './regional-vegetation.service';

@Controller()
export class ObservatoryController {
  constructor(private readonly observatory: ObservatoryService, private readonly map: MapService,
    private readonly nasa: NasaService, private readonly regional: RegionalVegetationService) {}

  @Get('health')
  health() { return { status: 'ok' }; }

  @Get('dashboard')
  dashboard(@Query('method') method?: string) {
    return { ...this.observatory.dashboard(method), liveMap: this.map.configured };
  }

  @Get('alerts')
  alerts(@Query('method') method?: string) { return this.observatory.watchlist(method); }

  @Get('bodies/:id/nasa')
  async satellite(@Param('id') id: string) {
    const point = this.observatory.location(id);
    const [power, catalog] = await Promise.all([this.nasa.power(point), this.nasa.granules(point)]);
    return { power, catalog, earthEngine: this.map.configured };
  }

  @Get('bodies/:id/nasa/catalog')
  extraCatalog(@Param('id') id: string) {
    return this.nasa.granules(this.observatory.location(id), true);
  }

  @Get('bodies/:id/climate')
  climate(@Param('id') id: string, @Query('month') month?: string) {
    if (!month || !/^20\d{2}-(0[1-9]|1[0-2])$/.test(month) || month >= new Date().toISOString().slice(0, 7)) {
      throw new BadRequestException('Elige un mes completo desde el año 2000.');
    }
    return this.map.compareClimate(this.observatory.location(id), month);
  }

  @Get('fires/recent')
  recentFires() { return this.nasa.fires(this.observatory.dashboard().results); }

  @Get('vegetation/regions')
  @Header('Cache-Control', 'public, max-age=3600')
  vegetationRegions() { return this.regional.regions(); }

  @Get('vegetation/timeline')
  @Header('Cache-Control', 'public, max-age=3600')
  vegetationTimeline() { return this.regional.timeline(); }

  @Get('vegetation/regions/:code')
  @Header('Cache-Control', 'public, max-age=3600')
  vegetationAnalysis(@Param('code') code: string) { return this.regional.analysis(code); }

  @Get('bodies/:id')
  detail(@Param('id') id: string, @Query('method') method?: string) { return this.observatory.detail(id, method); }

  @Get('bodies/:id/audit')
  audit(@Param('id') id: string, @Query('method') method?: string) { return this.observatory.history(id, method); }

  @Post('bodies/:id/reviews')
  review(@Param('id') id: string, @Body() body: Record<string, unknown>, @Query('method') method?: string) {
    return this.observatory.review(id, body, method);
  }

  @Get('weekly')
  weekly() { return this.observatory.weekly(); }

  @Get('fires/map')
  fireMap() { return this.observatory.fireMap(); }

  @Get('results.json')
  download(@Query('method') method?: string) {
    return new StreamableFile(this.observatory.download(method), {
      type: 'application/json', disposition: 'attachment; filename="uma_results.json"',
    });
  }

  @Get('images/:folder/:filename')
  image(@Param('folder') folder: string, @Param('filename') filename: string) {
    return new StreamableFile(this.observatory.image(folder, filename), { type: 'image/png' });
  }

  @Get('map/elevation')
  async elevation(@Query('body') body?: string) {
    const { results } = this.observatory.dashboard();
    const snapshot = body ? this.observatory.places(body).slice(0, 30) : results;
    return this.map.elevations(snapshot);
  }

  @Get('map/texture')
  async texture(@Query('mode') mode: string, @Query('year') input: string, @Query('fires') fires?: string) {
    const year = Number(input);
    if (!Number.isInteger(year) || year < 1985 || year > 2025 || (mode !== 'water' && mode !== 'landsat')) {
      throw new BadRequestException('Elige un modo de mapa y un año entre 1985 y 2025.');
    }
    return { url: await this.map.texture(mode, year, fires === 'true') };
  }
}
