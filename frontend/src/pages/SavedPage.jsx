import { useCallback, useEffect, useState } from 'react';
import { api, errorMessage } from '../api/client';

export default function SavedPage({ onOpen, onProcess }) {
  const [items, setItems] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const [tables, docs] = await Promise.all([api.get(`/api/timetables?limit=20&skip=${offset}`), api.get('/api/documents?limit=100')]);
      setItems(tables.data.items); setTotal(tables.data.total); setDocuments(docs.data.items);
    } catch (err) { setError(errorMessage(err)); }
    finally { setLoading(false); }
  }, [offset]);
  useEffect(() => { refresh(); }, [refresh]);
  async function remove(path, question) {
    if (!window.confirm(question)) return;
    setBusy(true);
    try { await api.delete(path); await refresh(); }
    catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }
  return <><div className="page-heading"><div><span className="eyebrow">YOUR WORKSPACE</span><h1>Saved timetables</h1><p className="muted">MongoDB stores your OCR drafts and corrected timetables.</p></div><button className="secondary" disabled={loading || busy} onClick={refresh}>Refresh</button></div>
    {error && <div className="alert error" role="alert">{error}</div>}
    <section className="panel">{loading ? <p role="status">Loading timetables…</p> : !items.length ? <div className="empty-state"><h2>No timetables on this page</h2><p>Upload and process a timetable to create your first draft.</p></div> : <div className="saved-list">{items.map(item => <article className="saved-item" key={item._id}><div><h2>{item.route_name || (item.table_type === 'destination_timetable' ? 'Destination timetable' : 'Untitled route')}</h2><p className="muted">{(item.entries || item.stops || []).length} rows · Updated {new Date(item.updated_at).toLocaleString()}</p><span className={`badge ${item.needs_review ? 'medium' : 'high'}`}>{item.status === 'saved' ? 'Saved' : 'OCR draft'}{item.needs_review ? ' · Needs review' : ' · Reviewed'}</span></div><div className="actions"><button className="secondary" disabled={busy} onClick={() => onOpen(item._id)}>Open editor</button><button className="text-button danger" disabled={busy} onClick={() => remove(`/api/timetables/${item._id}`, 'Delete this timetable? Its original uploaded document will remain.')}>Delete</button></div></article>)}</div>}
    <div className="pagination"><button className="secondary small" disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - 20))}>Previous</button><span>{total ? `${offset + 1}–${Math.min(offset + 20, total)} of ${total}` : '0 timetables'}</span><button className="secondary small" disabled={offset + 20 >= total || loading} onClick={() => setOffset(offset + 20)}>Next</button></div></section>
    <details className="panel originals"><summary>Original uploads (latest 100) — process or remove source files</summary><p className="muted">Originals are retained for preview and reprocessing. Deleting an original also removes all its timetables.</p>{documents.map(doc => <div className="document-item" key={doc._id}><div><strong>{doc.original_filename}</strong><small>{doc.page_count} page(s) · {doc.status}</small>{doc.error && <p className="danger">{doc.error}</p>}</div><div className="actions"><button className="secondary small" disabled={busy || doc.status === 'processing'} onClick={() => onProcess(doc)}>Process</button><button className="text-button danger" disabled={busy || doc.status === 'processing'} onClick={() => remove(`/api/documents/${doc._id}`, 'Permanently delete this original upload and ALL timetables extracted from it?')}>Delete original</button></div></div>)}</details>
  </>;
}
