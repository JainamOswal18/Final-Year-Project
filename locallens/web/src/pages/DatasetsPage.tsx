import { useRef, useState, type DragEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useDatasets } from "../auth";
import { timeAgo } from "../format";
import { Badge, Callout, Dialog, Field, Icon, Spinner, useToast } from "../ui";

function NewDatasetDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [name, setName] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const { reload } = useDatasets();
  const nav = useNavigate();
  const addFiles = (fl: FileList | null) => { if (fl) setFiles((x) => [...x, ...Array.from(fl)]); };
  const create = async () => {
    setBusy(true); setError("");
    try {
      const d = await api.createDataset(name.trim() || files[0]?.name.replace(/\.[^.]+$/, "") || "My data", files);
      await reload(); onClose(); setFiles([]); setName("");
      nav(`/d/${d.id}/columns`);
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const onDrop = (e: DragEvent) => { e.preventDefault(); setOver(false); addFiles(e.dataTransfer.files); };
  return (
    <Dialog open={open} onClose={onClose} title="New dataset"
      footer={<><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" disabled={busy || files.length === 0} onClick={() => void create()}>{busy ? <Spinner /> : null} Upload and continue</button></>}>
      <Field label="Name"><input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Retail sales" maxLength={80} /></Field>
      <div className={`drop ${over ? "over" : ""}`} role="button" tabIndex={0} onClick={() => input.current?.click()}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") input.current?.click(); }}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={onDrop}>
        <strong>Drop files here</strong> or click to choose<br />
        <span className="small">CSV, Excel, Parquet or SQLite. Several files become several tables.</span>
      </div>
      <input ref={input} type="file" multiple hidden accept=".csv,.tsv,.xlsx,.xls,.parquet,.sqlite,.sqlite3,.db" onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }} />
      {files.length > 0 && <div className="stack-sm">{files.map((f, i) => (
        <div className="row between small" key={i}><span>{f.name} <span className="faint">{(f.size / 1024 / 1024).toFixed(1)} MB</span></span>
          <button className="btn ghost sm" onClick={() => setFiles(files.filter((_, j) => j !== i))}>Remove</button></div>))}</div>}
      {error && <Callout kind="bad">{error}</Callout>}
      <div className="callout small stack-sm" style={{ display: "grid" }}>
        <strong>Before you upload</strong>
        <ul className="guide-list">
          <li>Put the column names in the <strong>first row</strong>, one row per sale, order or event.</li>
          <li>Have more than one file? Upload them together, for example <code>orders.csv</code> and <code>customers.csv</code>. You connect them next.</li>
          <li>Leave the name empty to use the file name.</li>
        </ul>
      </div>
      <p className="small muted">Files are stored on this server only. Next you will check which columns are metrics, categories and dates; a guide on that page explains how.</p>
    </Dialog>
  );
}

export default function DatasetsPage() {
  const { list, loading, reload } = useDatasets();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();
  const toast = useToast();
  const demo = async () => {
    setBusy(true);
    try { const d = await api.demoDataset(); await reload(); nav(`/d/${d.id}/ask`); }
    catch (e) { toast((e as Error).message, true); } finally { setBusy(false); }
  };
  return (
    <div className="page">
      <div className="page-head">
        <div><h1>Datasets</h1><p>Pick a dataset to ask questions, or add your own data.</p></div>
        <div className="row"><button className="btn" data-tour="demo" onClick={() => void demo()} disabled={busy}>{busy ? <Spinner /> : null} Try the retail demo</button>
          <button className="btn primary" data-tour="new-dataset" onClick={() => setOpen(true)}>{Icon.plus} New dataset</button></div>
      </div>
      {loading ? <Spinner /> : list.length === 0 ? (
        <div className="card empty">
          <h2>Add your first dataset</h2>
          <p className="muted" style={{ maxWidth: 460 }}>Upload spreadsheets or database files, check how each column is used, and start asking questions. Or look around with built-in sample retail data.</p>
          <div className="row"><button className="btn primary" onClick={() => setOpen(true)}>{Icon.plus} New dataset</button><button className="btn" onClick={() => void demo()}>Try the retail demo</button></div>
        </div>
      ) : (
        <div className="grid-cards">
          {list.map((d) => (
            <Link key={d.id} to={`/d/${d.id}/ask`} className="card pad hover stack-sm" style={{ textDecoration: "none", color: "inherit" }}>
              <div className="row between"><h3>{d.name}</h3>{d.visibility === "shared" ? <Badge kind="accent">Shared</Badge> : <Badge>Private</Badge>}</div>
              <div className="small muted">By {d.owner} · updated {timeAgo(d.updated_at)}</div>
            </Link>
          ))}
        </div>
      )}
      <NewDatasetDialog open={open} onClose={() => setOpen(false)} />
    </div>
  );
}
