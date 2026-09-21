import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { spawn, spawnSync } from 'node:child_process';
import net from 'node:net';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const windows = process.platform === 'win32';
const python = path.join(root, 'backend', '.venv', windows ? 'Scripts/python.exe' : 'bin/python');
const task = process.argv[2];

if (task === 'setup') {
  const command = windows ? 'powershell.exe' : 'bash';
  const args = windows ? ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', path.join(root, 'setup.ps1')] : [path.join(root, 'setup.sh')];
  const result = spawnSync(command, args, { cwd: root, stdio: 'inherit', windowsHide: true });
  if (result.error) console.error(result.error.message);
  process.exit(result.status ?? 1);
}

if (!existsSync(python)) { console.error('Backend virtual environment is missing. Run npm run setup first.'); process.exit(1); }
if (task === 'check') {
  const result = spawnSync(python, ['scripts/check_environment.py'], { cwd: root, stdio: 'inherit', windowsHide: true });
  process.exit(result.status ?? 1);
}
if (task !== 'dev') { console.error('Usage: node scripts/launch.mjs setup|dev|check'); process.exit(1); }
for (const relative of ['backend/.env', 'frontend/.env', 'frontend/node_modules/vite/bin/vite.js']) {
  if (!existsSync(path.join(root, relative))) { console.error(`${relative} is missing. Run npm run setup first.`); process.exit(1); }
}
const imported = spawnSync(python, ['-c', 'import backend.main'], { cwd: root, encoding: 'utf8', windowsHide: true });
if (imported.status !== 0) { console.error('Backend import failed. Run setup again.\n' + imported.stderr); process.exit(1); }
async function checkPort(port) {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once('error', () => reject(new Error(`Port ${port} is already in use. Stop the existing server before starting.`)));
    server.listen(port, '127.0.0.1', () => server.close(resolve));
  });
}
try { await Promise.all([checkPort(8000), checkPort(5173)]); }
catch (error) { console.error(error.message); process.exit(1); }

const children = [];
let stopping = false;
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  for (const child of children) {
    if (!child.pid || child.exitCode !== null) continue;
    if (windows) spawnSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore', windowsHide: true });
    else child.kill('SIGTERM');
  }
  process.exitCode = code;
}
function start(command, args, cwd) {
  const child = spawn(command, args, { cwd, stdio: 'inherit', windowsHide: true });
  children.push(child);
  child.on('error', error => { console.error(error.message); stop(1); });
  child.on('exit', code => { if (!stopping) { console.error(`A development server stopped (${code}).`); stop(code || 0); } });
}
start(python, ['-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', '8000'], root);
start(process.execPath, [path.join(root, 'frontend/node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', '5173', '--strictPort'], path.join(root, 'frontend'));
process.on('SIGINT', () => stop(0));
process.on('SIGTERM', () => stop(0));
console.log('\nFRONTEND: http://localhost:5173\nBACKEND: http://localhost:8000\nAPI DOCS: http://localhost:8000/docs\nPress Ctrl+C to stop both servers.\n');
