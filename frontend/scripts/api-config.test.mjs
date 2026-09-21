import assert from 'node:assert/strict';
import test from 'node:test';
import { resolveApiBase, backendConnectionMessage } from '../src/api/baseUrl.js';

test('development retains local backend access', () => {
  assert.equal(resolveApiBase(undefined, { development: true }), 'http://localhost:8000');
  assert.equal(resolveApiBase('http://127.0.0.1:8000/', { development: true }), 'http://127.0.0.1:8000');
});

test('production requires an explicitly configured public HTTPS backend', () => {
  for (const value of [undefined, '', 'http://localhost:8000', 'https://localhost:8000',
    'https://127.0.0.1:8000', 'https://[::1]:8000', 'https://192.168.1.2:8000',
    'https://10.0.0.2:8000', 'https://172.16.1.2:8000', 'http://api.example.com']) {
    assert.throws(() => resolveApiBase(value), /VITE_API_BASE_URL/);
  }
  assert.equal(resolveApiBase(' https://api.example.com/ '), 'https://api.example.com');
  assert.equal(resolveApiBase('https://demo.trycloudflare.com/'), 'https://demo.trycloudflare.com');
});

test('reject malformed endpoints and embedded credentials', () => {
  for (const value of ['not a URL', '/api', 'ftp://example.com', 'https://user:password@example.com',
    'https://api.example.com?secret=value', 'https://api.example.com#fragment']) {
    assert.throws(() => resolveApiBase(value), /VITE_API_BASE_URL/);
  }
});

test('phone users are not told to start a local FastAPI server', () => {
  assert.doesNotMatch(backendConnectionMessage(false), /localhost|FastAPI|Start/);
  assert.match(backendConnectionMessage(true), /development server/);
});
