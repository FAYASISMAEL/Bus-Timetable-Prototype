// Exercises the real React components against the running API in a DOM test
// environment. This is not a substitute for browser layout inspection.
import assert from 'node:assert/strict';
import { mkdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const root = path.resolve(frontend, '..');
const base = 'http://localhost:8000';
const request = globalThis.fetch;
const NativeFormData = globalThis.FormData;
const NativeBlob = globalThis.Blob;
let documentId;
let reactRoot;
let reactAct;
let dom;
const errors = [];
const originalError = console.error;
console.error = (...args) => { errors.push(args.join(' ')); originalError(...args); };

async function jsonRequest(route, options) {
  const response = await request(base + route, options);
  assert.ok(response.ok, `${route}: ${response.status} ${response.ok ? '' : await response.text()}`);
  return response.json();
}

try {
  const health = await jsonRequest('/api/health');
  assert.equal(health.status, 'ok', 'Start MongoDB and configure English OCR before this live UI test.');
  await mkdir(path.join(root, '.runtime'), { recursive: true });
  const form = new NativeFormData();
  form.append('file', new NativeBlob([await readFile(path.join(root, 'backend/uploads/6ab0e5cd1bdf536b2bc5f00a.pdf'))], { type: 'application/pdf' }), 'ui-table-test.pdf');
  const source = await jsonRequest('/api/upload', { method: 'POST', body: form });
  documentId = source._id;
  const timetable = await jsonRequest(`/api/process/${documentId}`, { method: 'POST' });
  assert.equal(timetable.entries.length, 20);
  assert.equal(timetable.extraction_method, 'DIRECT_TEXT');
  assert.equal(timetable.entries[2].destination, 'Ernakulam');
  assert.equal(timetable.entries[2].timing, '07:45');

  dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', { url: 'http://localhost:5173', pretendToBeVisual: true });
  for (const key of ['window', 'document', 'HTMLElement', 'HTMLInputElement', 'XMLHttpRequest', 'FormData', 'File', 'Blob', 'Event', 'MouseEvent', 'location']) globalThis[key] = dom.window[key];
  Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator, configurable: true });
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const downloads = [];
  globalThis.URL.createObjectURL = blob => { downloads.push(blob); return 'blob:test-download'; };
  globalThis.URL.revokeObjectURL = () => {};
  dom.window.HTMLAnchorElement.prototype.click = function () {};
  dom.window.confirm = () => true;

  await build({ entryPoints: [path.join(frontend, 'src/App.jsx')], outfile: path.join(frontend, '.runtime/App.mjs'), bundle: true, format: 'esm', platform: 'node', jsx: 'automatic', external: ['react', 'react-dom', 'axios'], define: { 'import.meta.env': '{}' } });
  const { default: React, act } = await import('react');
  reactAct = act;
  const { createRoot } = await import('react-dom/client');
  const { default: App } = await import(pathToFileURL(path.join(frontend, '.runtime/App.mjs')));
  const text = () => document.body.textContent;
  const button = label => [...document.querySelectorAll('button')].find(item => item.textContent.trim() === label);
  async function waitFor(condition, message) {
    const started = Date.now();
    while (!condition()) {
      if (Date.now() - started > 15000) throw new Error(`Timed out: ${message}\n${text()}`);
      await act(async () => { await new Promise(resolve => setTimeout(resolve, 100)); });
    }
  }
  async function click(label) {
    const element = button(label);
    assert.ok(element, `Missing button ${label}`);
    assert.equal(element.disabled, false, `Disabled button ${label}`);
    await act(async () => { element.dispatchEvent(new MouseEvent('click', { bubbles: true })); });
  }
  reactRoot = createRoot(document.getElementById('root'));
  await act(async () => { reactRoot.render(React.createElement(App)); });
  await waitFor(() => text().includes('Malayalam OCR Available') && text().includes('MongoDB Connected'), 'healthy status indicators');
  assert.ok(text().includes('Smart Timetable Digitizer'));

  const fileInput = document.querySelector('input[type=file]');
  Object.defineProperty(fileInput, 'files', { configurable: true, value: [new File(['invalid'], 'bad.exe', { type: 'application/octet-stream' })] });
  await act(async () => { fileInput.dispatchEvent(new Event('change', { bubbles: true })); });
  assert.ok(text().includes('Unsupported file type'));

  // A valid selection renders once before its object URL effect runs. This
  // guards against dereferencing the still-null uploaded document in that gap.
  Object.defineProperty(fileInput, 'files', { configurable: true, value: [new File(['%PDF-1.7'], 'preview.pdf', { type: 'application/pdf' })] });
  await act(async () => { fileInput.dispatchEvent(new Event('change', { bubbles: true })); });
  await waitFor(() => document.querySelector('iframe[title="PDF preview: preview.pdf"]'), 'local PDF preview');
  assert.ok(!text().includes('Something went wrong'));
  assert.equal(button('Upload timetable').disabled, false);

  await click('Saved timetables');
  await waitFor(() => text().includes('Destination timetable'), 'saved timetable listing');
  const ownItem = [...document.querySelectorAll('article.saved-item')].find(item => item.textContent.includes('Destination timetable'));
  await act(async () => { ownItem.querySelector('button').dispatchEvent(new MouseEvent('click', { bubbles: true })); });
  await waitFor(() => document.querySelector('input[aria-label="Destination 1"]'), 'editor rows');
  assert.deepEqual([...document.querySelectorAll('.editor-table th')].map(node => node.textContent), ['Destination', 'Timing', 'Confidence', 'Review']);
  assert.ok(text().includes('Extraction method: Direct PDF Text'));
  assert.equal(document.querySelector('.route-fields'), null);
  assert.ok(!document.querySelector('.editor-table').textContent.includes('Sl. No.'));
  assert.equal(document.querySelector('input[aria-label="Destination 3"]').value, 'Ernakulam');
  assert.equal(document.querySelector('input[aria-label="Timing 3"]').value, '07:45');
  const stop = document.querySelector('input[aria-label="Destination 1"]');
  const inputSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  await act(async () => { inputSetter.call(stop, 'ആലുവ corrected'); stop.dispatchEvent(new Event('input', { bubbles: true })); });
  assert.ok(text().includes('Unsaved changes'));
  await click('Save Corrections');
  await waitFor(() => text().includes('Corrections saved to MongoDB'), 'save correction');
  const saved = await jsonRequest(`/api/timetables/${timetable._id}`);
  assert.equal(saved.entries[0].destination, 'ആലുവ corrected');
  assert.deepEqual(saved.entries.map(row => row.sl_no), Array.from({length: 20}, (_, i) => i + 1));
  assert.equal(saved.route_name, null);
  const objectUrlsBeforeExport = downloads.length;
  await click('Export JSON');
  await waitFor(() => text().includes('JSON exported'), 'JSON download');
  await click('Export CSV');
  await waitFor(() => text().includes('CSV exported'), 'CSV download');
  assert.equal(downloads.length, objectUrlsBeforeExport + 2);
  assert.equal(errors.length, 0, 'React rendered without console errors');
  await act(async () => { reactRoot.unmount(); });
  reactRoot = null;
  console.log('PASS: React mounts, direct PDF extraction, 20 rows, exact four editor columns, hidden serials, row ordering, correction/save, JSON/CSV downloads; no console errors.');
} finally {
  if (reactRoot && reactAct) await reactAct(async () => { reactRoot.unmount(); });
  if (dom) dom.window.close();
  console.error = originalError;
  if (documentId) await request(`${base}/api/documents/${documentId}`, { method: 'DELETE' });
}
