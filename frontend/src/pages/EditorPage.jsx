import { useState } from 'react';
import { api, downloadTimetable, errorMessage, sourceUrl } from '../api/client';
import SourcePreview from '../components/SourcePreview';

const sortEntries = rows => [...rows].sort((a, b) => (a.sl_no ?? Infinity) - (b.sl_no ?? Infinity));
const validTime = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
function issuesFor(row, rows, structured) {
  if (structured) {
    const issues = [];
    if (!row.destination.trim()) issues.push('Missing destination');
    if (!validTime.test(row.timing || '')) issues.push('Invalid or missing timing (HH:MM)');
    if (!Number.isInteger(row.sl_no) || row.sl_no < 1) issues.push('Missing or invalid row anchor');
    else if (rows.filter(other => other.sl_no === row.sl_no).length > 1) issues.push('Duplicate row anchor');
    if ((row.destination || row.timing) && rows.filter(other => other.destination.trim() === row.destination.trim() && other.timing === row.timing).length > 1) issues.push('Duplicate row');
    if (row.confidence < 60 && !row.reviewed) issues.push('Low extraction confidence');
    if (row.ambiguous && !row.reviewed) issues.push('Check layout against source');
    return issues;
  }
  const issues = [];
  if (!row.stop_name.trim()) issues.push('Missing stop name');
  if (!validTime.test(row.time)) issues.push('Invalid or missing time (HH:MM)');
  if (rows.filter(other => other.stop_name.trim().toLowerCase() === row.stop_name.trim().toLowerCase() && other.time === row.time && other.trip_index === row.trip_index).length > 1) issues.push('Duplicate row');
  if (row.confidence < 60 && !row.reviewed) issues.push('Low OCR confidence');
  if (row.ambiguous && !row.reviewed) issues.push('Check layout against source');
  if (row.stop_name && (!/\p{L}/u.test(row.stop_name) || /[�?@#=]|(.)\1{4,}/u.test(row.stop_name))) issues.push('Suspicious stop text');
  return issues;
}

export default function EditorPage({ timetable, document, onSaved, onProcess, dirty, setDirty }) {
  const [draft, setDraft] = useState(() => timetable.table_type === 'destination_timetable' ? { ...timetable, entries: sortEntries(timetable.entries) } : timetable);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const structured = draft.table_type === 'destination_timetable';
  const rowsKey = structured ? 'entries' : 'stops';
  const rows = draft[rowsKey];
  const nameKey = structured ? 'destination' : 'stop_name';
  const timeKey = structured ? 'timing' : 'time';
  function change(key, value) { setDraft(previous => ({ ...previous, [key]: value })); setDirty(true); setNotice(''); }
  function changeRow(index, key, value) { change(rowsKey, rows.map((row, i) => i === index ? { ...row, [key]: value } : row)); }
  async function save() {
    const { route_name, origin, destination, stops, revision } = draft;
    const payload = structured ? { entries: draft.entries, revision } : { route_name, origin, destination, stops, revision };
    const { data } = await api.put(`/api/timetables/${draft._id}`, payload);
    setDraft(data); onSaved(data); setDirty(false);
    return data;
  }
  async function action(format) {
    setBusy(true); setError(''); setNotice('');
    try {
      if (dirty || !format) await save();
      if (format) { await downloadTimetable(draft._id, format); setNotice(`${format.toUpperCase()} exported with your latest saved corrections.`); }
      else setNotice('Corrections saved to MongoDB. Unresolved rows are retained for review.');
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }
  function addRow() {
    if (structured) {
      change(rowsKey, [...rows, { sl_no: Math.max(0, ...rows.map(row => row.sl_no || 0)) + 1, destination: '', timing: null, confidence: 0, reviewed: true, ambiguous: false, page: 1, needs_review: true }]);
      return;
    }
    change(rowsKey, [...rows, { stop_name: '', time: '', confidence: 0, original_text: '', original_time: '', normalized_text: '', page: 1, trip_index: 1, reviewed: true, ambiguous: false, issues: [], confidence_level: 'low', needs_review: true }]);
  }
  const reviewCount = rows.filter(row => issuesFor(row, rows, structured).length).length;
  return <>
    <div className="page-heading"><div><span className="eyebrow">EXTRACT & REVIEW</span><h1>Timetable editor</h1><p className="muted">{document?.original_filename} · {rows.length} rows · {reviewCount} need review</p></div><span className={`badge ${dirty ? 'medium' : 'high'}`}>{dirty ? 'Unsaved changes' : draft.status === 'saved' ? 'Saved to MongoDB' : 'Extraction draft'}</span></div>
    {draft.extraction_method && <p className="muted small-text">Extraction method: {{ DIRECT_TEXT: 'Direct PDF Text', OCR_FALLBACK: 'OCR Scan', MIXED: 'Direct PDF Text + OCR Scan' }[draft.extraction_method]}</p>}
    {error && <div className="alert error" role="alert">{error}</div>}{notice && <div className="alert success" role="status">{notice}</div>}
    <div className="editor-grid"><section className="panel">
      <fieldset disabled={busy} className="editor-fields"><legend className="sr-only">Edit timetable</legend>
        {!structured && <div className="route-fields">{[['route_name', 'Route name'], ['origin', 'Origin'], ['destination', 'Destination']].map(([key, label]) => <label key={key}>{label}<input value={draft[key] || ''} maxLength={500} onChange={e => change(key, e.target.value)} placeholder={label} /></label>)}</div>}
        {draft.warnings?.length > 0 && <details className="parser-notes" open><summary>Extraction notes — verify against the source</summary><ul>{draft.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul></details>}
        <div className="section-heading"><h2>{structured ? 'Destinations & timings' : 'Stops & times'}</h2><button className="secondary small" onClick={addRow} disabled={rows.length >= 3000}>+ Add row</button></div>
        <p className="muted small-text">Times use 24-hour HH:MM. Extraction confidence stays unchanged after editing. Mark a row reviewed after checking the source.</p>
        <div className="table-scroll"><table className="editor-table"><thead><tr><th scope="col">{structured ? 'Destination' : 'Stop'}</th><th scope="col">{structured ? 'Timing' : 'Time'}</th><th scope="col">Confidence</th><th scope="col">Review</th></tr></thead><tbody>{rows.map((row, index) => {
          const issues = issuesFor(row, rows, structured);
          const level = row.confidence >= 80 ? 'high' : row.confidence >= 60 ? 'medium' : 'low';
          return <tr key={index} className={issues.length ? 'needs-review' : ''}><td><input aria-label={`${structured ? 'Destination' : 'Stop'} ${index + 1}`} aria-invalid={!row[nameKey].trim()} value={row[nameKey]} maxLength={500} onChange={e => changeRow(index, nameKey, e.target.value)} /><small>Page {row.page}</small><details className="original"><summary>Original extracted cells</summary><span>{(structured ? row.original_destination : row.original_text) || '(no destination detected)'} · {row.original_time || '(no time detected)'}</span></details></td><td><input className="time-input" aria-label={`${structured ? 'Timing' : 'Time'} ${index + 1}`} aria-invalid={!validTime.test(row[timeKey])} value={row[timeKey] || ''} maxLength={40} placeholder="HH:MM" onChange={e => changeRow(index, timeKey, e.target.value)} /></td><td><span className={`badge ${level}`}>{Math.round(row.confidence)}% · {level}</span></td><td><div className="row-issues">{issues.length ? issues.map(issue => <span key={issue}>{issue}</span>) : <span className="valid">OK</span>}</div><label className="review-check"><input type="checkbox" checked={!!row.reviewed} onChange={e => changeRow(index, 'reviewed', e.target.checked)} /> Reviewed</label><button className="text-button danger" aria-label={`Remove row ${index + 1}`} onClick={() => change(rowsKey, rows.filter((_, i) => i !== index))}>Remove</button></td></tr>;
        })}</tbody></table></div>
        {!rows.length && <div className="empty-state"><p>No rows yet. Add a row or process a clearer image.</p><button className="secondary" onClick={addRow}>Add first row</button></div>}
      </fieldset>
      <div className="actions editor-actions"><button disabled={busy} onClick={() => action()}>{busy ? 'Working…' : 'Save Corrections'}</button><button className="secondary" disabled={busy} onClick={() => action('json')}>Export JSON</button><button className="secondary" disabled={busy} onClick={() => action('csv')}>Export CSV</button><button className="text-button" disabled={busy || !document} onClick={() => onProcess(document)}>Process Again</button></div>
      <p className="muted small-text">Exports save your current edits first. Processing again creates a separate draft and keeps saved corrections.</p>
    </section><aside className="panel source-panel"><h2>Original document</h2>{document && <SourcePreview url={sourceUrl(document._id)} type={document.file_type} name={document.original_filename} />}<p className="muted small-text">Click an image to inspect it at full size. Bounding boxes in the document API refer to the processed page.</p><details><summary>Page processing details</summary>{draft.pages?.map(page => <p key={page.page}>Page {page.page}: {page.token_count} tokens, {page.width} × {page.height}, {page.mode === 'DIRECT_TEXT' ? 'Direct PDF Text' : 'OCR Scan'}, deskew {page.deskew_degrees || 0}°{page.perspective_corrected ? ', perspective corrected' : ''}</p>)}</details></aside></div>
    <details className="panel raw-text"><summary>Raw extracted text</summary><pre>{draft.raw_ocr_text || 'No text detected.'}</pre></details>
  </>;
}
