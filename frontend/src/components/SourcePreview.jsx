export default function SourcePreview({ url, type, name }) {
  if (!url) return null;
  return <div className="source-preview">{type === 'application/pdf'
    ? <><iframe title={`PDF preview: ${name}`} src={url} /><a href={url} target="_blank" rel="noreferrer">Open PDF in a new tab</a></>
    : <a href={url} target="_blank" rel="noreferrer"><img src={url} alt={`Original timetable: ${name}`} /></a>}</div>;
}
