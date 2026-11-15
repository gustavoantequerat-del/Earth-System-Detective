const { copyFileSync, mkdirSync, readdirSync } = require('node:fs');
const { dirname, join, resolve } = require('node:path');

const root = resolve(__dirname, '../..');
const output = resolve(__dirname, '../dist/observatory-data');
const files = [
  'config/settings.json',
  'data/national/results.json',
  'data/national/agua_artificial.json',
  'data/real/alertas_semanales.json',
  'data/real/fires-map.json',
  'data/real/vegetation-regions.json.gz',
  'Naseros/data/bol_admin2_simplified.geojson.gz',
  'data/real/verificacion.json',
  'data/real/desaguadero.json',
];

for (const mode of ['real', 'sample']) {
  for (const file of ['results.json', 'suspects.csv', 'series.csv', 'uma.db', 'validation/results.json', 'validation/uma.db']) {
    files.push(`data/${mode}/${file}`);
  }
}
files.push('data/real/basins.csv');

for (const folder of ['data/real/context', 'data/real/img']) {
  for (const file of readdirSync(join(root, folder), { withFileTypes: true })) {
    if (file.isFile() && /\.(png|json)$/.test(file.name)) files.push(`${folder}/${file.name}`);
  }
}

for (const file of files) {
  const destination = join(output, file);
  mkdirSync(dirname(destination), { recursive: true });
  copyFileSync(join(root, file), destination);
}

console.log(`NestJS incluye ${files.length} archivos de datos e imágenes.`);
