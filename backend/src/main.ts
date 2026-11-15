import 'reflect-metadata';
import { resolve } from 'node:path';
import { config } from 'dotenv';
import { NestFactory } from '@nestjs/core';
import { Module } from '@nestjs/common';
import { ObservatoryController } from './observatory.controller';
import { ObservatoryService } from './observatory.service';
import { MapService } from './map.service';
import { NasaService } from './nasa.service';
import { RegionalVegetationService } from './regional-vegetation.service';

@Module({
  controllers: [ObservatoryController],
  providers: [ObservatoryService, MapService, NasaService, RegionalVegetationService],
})
class AppModule {}

async function main() {
  config({ path: [resolve(__dirname, '../.env'), resolve(__dirname, '../../.env')], quiet: true });
  const app = await NestFactory.create(AppModule);
  app.setGlobalPrefix('api');
  await app.listen(process.env.PORT ?? 3001, process.env.HOST ?? '127.0.0.1');
}

void main();
