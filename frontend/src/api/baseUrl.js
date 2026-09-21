const localHostname = hostname => {
  const host = hostname.toLowerCase().replace(/^\[|\]$/g, '');
  if (host === 'localhost' || host.endsWith('.localhost') || host.endsWith('.local') ||
      host === '::1' || host === '::' || /^(fc|fd|fe80:)/.test(host) && host.includes(':')) return true;
  const octets = host.split('.').map(Number);
  if (octets.length !== 4 || octets.some(value => !Number.isInteger(value))) return false;
  return octets[0] === 0 || octets[0] === 127 || octets[0] === 10 ||
    octets[0] === 192 && octets[1] === 168 ||
    octets[0] === 172 && octets[1] >= 16 && octets[1] <= 31 ||
    octets[0] === 169 && octets[1] === 254;
};

export function resolveApiBase(value, { development = false } = {}) {
  const configured = value?.trim() || (development ? 'http://localhost:8000' : '');
  if (!configured) {
    throw new Error('Set VITE_API_BASE_URL to the public HTTPS FastAPI backend URL before building. Mobile devices cannot connect to your laptop through localhost.');
  }
  let url;
  try { url = new URL(configured); }
  catch { throw new Error('VITE_API_BASE_URL must be an absolute backend URL.'); }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new Error('VITE_API_BASE_URL must be an HTTP(S) backend URL without credentials, a query or a fragment.');
  }
  if (!development && (url.protocol !== 'https:' || localHostname(url.hostname))) {
    throw new Error('Production VITE_API_BASE_URL must use a public HTTPS backend, not localhost or a private network address. Deploy FastAPI or configure an HTTPS demo tunnel, then rebuild.');
  }
  return url.href.replace(/\/+$/, '');
}

export function backendConnectionMessage(development) {
  return development
    ? 'Could not connect to the local backend. Start the development server and try again.'
    : 'The timetable server is unavailable. Please try again shortly or contact the site owner.';
}
