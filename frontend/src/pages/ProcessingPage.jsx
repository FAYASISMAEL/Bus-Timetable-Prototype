import { useEffect, useState } from 'react';

export default function ProcessingPage({ document }) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => { const timer = setInterval(() => setElapsed(s => s + 1), 1000); return () => clearInterval(timer); }, []);
  return <section className="panel processing" aria-live="polite"><div className="spinner" /><span className="eyebrow">READING YOUR TIMETABLE</span><h1>Processing {document.original_filename}</h1><p>Reading PDF text and table positions, using OCR only for scanned pages, then validating rows.</p><p className="muted">{document.page_count} page(s) · {elapsed}s elapsed</p><p>This can take a minute per page. Keep this tab open until the editor appears.</p></section>;
}
