import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const vite = path.join(frontend, 'node_modules', 'vite', 'bin', 'vite.js');

if (!existsSync(vite)) {
  console.error('Vite is not installed in frontend/node_modules.');
  console.error('From the project root, run: npm --prefix frontend install');
  process.exit(1);
}
