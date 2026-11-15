const { execFileSync } = require('node:child_process');
const { writeFileSync } = require('node:fs');
const { resolve } = require('node:path');

const root = resolve(__dirname, '../..');
const ref = process.argv[2] ?? 'origin/mapa3';
const source = 'Bolivia/salidas/mapa_3d.html';
const commit = execFileSync('git', ['rev-parse', '--verify', '--end-of-options', ref + '^{commit}'], { cwd: root, encoding: 'utf8' }).trim();
const html = execFileSync('git', ['show', `${commit}:${source}`], { cwd: root, encoding: 'utf8', maxBuffer: 4 * 1024 * 1024 });
const embedded = html.match(/<script id="data" type="application\/json">([^<]+)<\/script>/)?.[1];
if (!embedded) throw new Error('El mapa 3D de incendios no contiene su bloque de datos.');

const data = JSON.parse(embedded);
const cells = data.lat.length;
if (!cells || data.lon.length !== cells || data.counts.length !== data.months.length * cells ||
    data.forecasts.some(({ val }) => val.length !== cells) || data.model_anom.val.length !== cells) {
  throw new Error('Las series no coinciden con la grilla del mapa de incendios.');
}
writeFileSync(resolve(root, 'data/real/fires-map.json'), JSON.stringify({ source: { commit, file: source }, ...data }) + '\n');
console.log(`${data.months.length} meses y ${cells} celdas importados de ${commit.slice(0, 7)}.`);
