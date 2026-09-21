import { useEffect, useState } from 'react';
import { api, errorMessage } from './api/client';
import SystemStatus from './components/SystemStatus';
import UploadPage from './pages/UploadPage';
import ProcessingPage from './pages/ProcessingPage';
import EditorPage from './pages/EditorPage';
import SavedPage from './pages/SavedPage';

export default function App() {
  const [page, setPage] = useState('upload');
  const [document, setDocument] = useState(null);
  const [timetable, setTimetable] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState('');
  const [opening, setOpening] = useState(false);
  useEffect(() => {
    const handler = event => { if (dirty || page === 'processing') { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [dirty, page]);
  function canLeave() { return !dirty || window.confirm('Leave the editor and discard unsaved changes?'); }
  function navigate(next) {
    if (next === page || !canLeave()) return;
    setDirty(false); setError(''); setPage(next);
  }
  async function process(doc) {
    if (!canLeave()) return;
    setDirty(false); setError(''); setDocument(doc); setPage('processing');
    try {
      const { data } = await api.post(`/api/process/${doc._id}`, null, { timeout: 1500000 });
      setTimetable(data); setPage('editor');
    } catch (err) { setError(errorMessage(err)); setPage('upload'); }
  }
  async function open(id) {
    setOpening(true); setError('');
    try {
      const { data } = await api.get(`/api/timetables/${id}`);
      const source = await api.get(`/api/documents/${data.document_id}`);
      setTimetable(data); setDocument(source.data); setDirty(false); setPage('editor');
    } catch (err) { setError(errorMessage(err)); }
    finally { setOpening(false); }
  }
  const blocked = page === 'processing' || opening;
  return <><header className="topbar"><div className="shell nav-inner"><button className="brand" disabled={blocked} onClick={() => navigate('upload')}><span className="brand-mark" aria-hidden="true">▦</span> Smart Timetable <span className="prototype">SC-04</span></button><nav aria-label="Main navigation"><button disabled={blocked} className={page === 'upload' ? 'nav-link selected' : 'nav-link'} onClick={() => navigate('upload')}>Upload</button><button disabled={blocked} className={page === 'saved' ? 'nav-link selected' : 'nav-link'} onClick={() => navigate('saved')}>Saved timetables</button></nav></div></header>
    <main className="shell"><SystemStatus />{error && <div className="alert error" role="alert">{error}<button className="text-button" onClick={() => setError('')}>Dismiss</button></div>}{opening && <p role="status">Opening timetable…</p>}
      {page === 'upload' && <UploadPage document={document} setDocument={setDocument} onProcess={process} />}
      {page === 'processing' && <ProcessingPage document={document} />}
      {page === 'editor' && timetable && <EditorPage key={timetable._id} timetable={timetable} document={document} onSaved={setTimetable} onProcess={process} dirty={dirty} setDirty={setDirty} />}
      {page === 'saved' && <SavedPage onOpen={open} onProcess={process} />}
    </main><footer className="shell footer">Smart Timetable Digitizer <span>Printed schedules. Editable data.</span></footer>
  </>;
}
