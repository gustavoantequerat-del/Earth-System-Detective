import { existsSync } from 'node:fs';
import { join, resolve } from 'node:path';

export function dataRoot() {
  const repository = resolve(__dirname, '../..');
  if (process.env.VERCEL !== '1' && existsSync(join(repository, 'data', 'real', 'results.json'))) {
    return repository;
  }
  const packaged = join(__dirname, 'observatory-data');
  if (existsSync(join(packaged, 'data', 'real', 'results.json'))) return packaged;
  return repository;
}
