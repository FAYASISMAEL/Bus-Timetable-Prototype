import axios from 'axios';
import { resolveApiBase, backendConnectionMessage } from './baseUrl';

export const API_BASE = resolveApiBase(import.meta.env.VITE_API_BASE_URL, { development: import.meta.env.DEV });
export const CONNECTION_MESSAGE = backendConnectionMessage(import.meta.env.DEV);
export const api = axios.create({ baseURL: API_BASE, timeout: 20000 });
export const sourceUrl = id => `${API_BASE}/api/documents/${encodeURIComponent(id)}/source`;

export function errorMessage(error) {
  const response = error?.response;
  if (!response) return error?.code === 'ECONNABORTED'
    ? 'The request timed out. Check the document status before retrying.'
    : CONNECTION_MESSAGE;
  const data = response.data;
  return data?.error?.message || (typeof data?.detail === 'string' ? data.detail : 'The request could not be completed. Please try again.');
}

export async function downloadTimetable(id, format) {
  let response;
  try {
    response = await api.get(`/api/timetables/${id}/export/${format}`, { responseType: 'blob' });
  } catch (error) {
    if (error.response?.data instanceof Blob) {
      try { error.response.data = JSON.parse(await error.response.data.text()); } catch { /* use safe fallback */ }
    }
    throw error;
  }
  const url = URL.createObjectURL(response.data);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `timetable-${id}.${format}`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
