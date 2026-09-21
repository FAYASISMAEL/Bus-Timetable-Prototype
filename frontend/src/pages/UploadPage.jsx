import { useEffect, useRef, useState } from 'react';
import { api, errorMessage, sourceUrl } from '../api/client';
import SourcePreview from '../components/SourcePreview';

export default function UploadPage({ onProcess, document, setDocument }) {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState('');
  const [error, setError] = useState('');
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [dragging, setDragging] = useState(false);
  const input = useRef(null);
  useEffect(() => {
    if (!file) { setPreview(''); return; }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  function choose(candidate) {
    if (!candidate || uploading) return;
    setError('');
    if (!/\.(jpe?g|png|pdf)$/i.test(candidate.name)) { setError('Unsupported file type. Use JPG, JPEG, PNG, or PDF.'); return; }
    if (!candidate.size) { setError('The selected file is empty.'); return; }
    if (candidate.size > 15 * 1024 * 1024) { setError('File is too large. Maximum size is 15 MB.'); return; }
    setFile(candidate); setDocument(null);
  }
  async function upload() {
    setUploading(true); setError(''); setProgress(0);
    try {
      const body = new FormData(); body.append('file', file);
      const { data } = await api.post('/api/upload', body, { onUploadProgress: event => setProgress(Math.round((event.loaded / (event.total || file.size)) * 100)) });
      setDocument(data);
    } catch (err) { setError(errorMessage(err)); }
    finally { setUploading(false); }
  }
  return <>
    <section className="intro"><span className="eyebrow">PRINT TO DATA · ENGLISH + മലയാളം</span><h1>Smart Timetable Digitizer</h1><p>Convert printed bus timetables into structured digital data</p></section>
    <div className="workflow" aria-label="Workflow"><span className="active">1 <b>Upload a timetable</b></span><span>2 <b>Extract & review</b></span><span>3 <b>Save & export</b></span></div>
    {error && <div role="alert" className="alert error">{error}</div>}
    <section className="panel upload-panel">
      <div><h2>Start with your printed timetable</h2><p className="muted">Use a clear, upright photo or a scanned PDF. You can correct every extracted row.</p>
        <div className={`drop-zone ${dragging ? 'dragging' : ''}`} onDragOver={event => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={event => { event.preventDefault(); setDragging(false); choose(event.dataTransfer.files[0]); }}>
          <span className="upload-icon" aria-hidden="true">↑</span><h3>Drop your file here</h3><p>or select one from your computer</p><button onClick={() => input.current.click()} disabled={uploading} className="secondary">Choose file</button>
          <input ref={input} aria-label="Choose timetable file" type="file" accept=".jpg,.jpeg,.png,.pdf" hidden onChange={event => { choose(event.target.files[0]); event.target.value = ''; }} />
          <small>JPG, JPEG, PNG, PDF · up to 15 MB · up to 10 PDF pages</small>
        </div>
        {(file || document) && <div className="file-summary"><strong>{file?.name || document.original_filename}</strong><span>{((file?.size || document.size_bytes) / 1048576).toFixed(2)} MB{document ? ` · ${document.page_count} page(s) · Uploaded` : ' · Ready to upload'}</span></div>}
        <div className="actions">{!document ? <button disabled={!file || uploading} onClick={upload}>{uploading ? `Uploading ${progress}%…` : 'Upload timetable'}</button> : <button onClick={() => onProcess(document)}>Process timetable →</button>}</div>
        {document && <p className="muted">Upload validated. Processing reads PDF text directly and uses English OCR for scans by default.</p>}
      </div>
      <aside><h3>Source preview</h3>{file || document ? <SourcePreview url={preview || (document ? sourceUrl(document._id) : '')} type={file?.type || document?.file_type || (/\.pdf$/i.test(file?.name || '') ? 'application/pdf' : 'image/png')} name={file?.name || document?.original_filename} /> : <div className="preview-empty"><span aria-hidden="true">▤</span><p>Your timetable will appear here</p><small>All pages in a PDF are processed.</small></div>}</aside>
    </section>
    <p className="footnote">Automatic extraction is a starting point. Review destinations and uncertain times before using the data.</p>
  </>;
}
