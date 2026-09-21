import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';

export default function SystemStatus() {
  const [status, setStatus] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const refresh = useCallback(async () => {
    setLoading(true);
    const results = await Promise.allSettled([
      api.get('/api/health'), api.get('/api/system/ocr-status'), api.get('/api/system/database-status'),
    ]);
    setStatus(results[0].status === 'fulfilled' ? results[0].value.data : { backend: false });
    setMessages(results.slice(1).flatMap(result => result.status === 'fulfilled' && !(result.value.data.ready ?? result.value.data.connected) ? [result.value.data.message] : []));
    setLoading(false);
  }, []);
  useEffect(() => { refresh(); const timer = setInterval(refresh, 30000); return () => clearInterval(timer); }, [refresh]);
  const items = [['backend', 'Backend', 'Connected', 'Disconnected'], ['mongodb', 'MongoDB', 'Connected', 'Disconnected'], ['tesseract', 'Tesseract', 'Installed', 'Missing'], ['english_ocr', 'English OCR', 'Available', 'Missing'], ['malayalam_ocr', 'Malayalam OCR', 'Available', 'Missing']];
  return <section className="system-status" aria-label="System status">
    <div className="status-bar">{items.map(([key, name, good, bad]) => <span className="status-item" key={key}><i className={`dot ${status?.[key] ? 'good' : status ? 'bad' : ''}`} /><span>{name} <strong>{!status ? 'Checking…' : status[key] === undefined ? 'Unknown' : status[key] ? good : bad}</strong></span></span>)}<button className="text-button" onClick={refresh} disabled={loading}>{loading ? 'Checking…' : 'Refresh'}</button></div>
    {status && !status.backend && <p className="status-note">Could not connect to backend. Start FastAPI at localhost:8000.</p>}
    {messages.length > 0 && <details className="status-note"><summary>Setup needs attention ({messages.length})</summary>{messages.map(message => <p key={message}>{message}</p>)}<p>See the setup and troubleshooting instructions in README.md, then refresh.</p></details>}
  </section>;
}
