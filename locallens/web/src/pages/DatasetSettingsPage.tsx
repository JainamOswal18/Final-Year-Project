import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useDatasets } from "../auth";
import { Callout, Dialog, Field, useToast } from "../ui";
import { PageHead, useDataset } from "./DatasetLoader";

export default function DatasetSettingsPage() {
  const { detail, reload } = useDataset();
  const { reload: reloadList } = useDatasets();
  const [name, setName] = useState(detail.name);
  const [confirm, setConfirm] = useState(false);
  const toast = useToast();
  const nav = useNavigate();
  const save = async (body: { name?: string; visibility?: string }) => {
    try { await api.patchDataset(detail.id, body); await reload(); toast("Saved."); } catch (e) { toast((e as Error).message, true); }
  };
  const remove = async () => {
    try { await api.deleteDataset(detail.id); await reloadList(); toast("Dataset deleted."); nav("/datasets"); } catch (e) { toast((e as Error).message, true); setConfirm(false); }
  };
  return (
    <div className="page">
      <PageHead title="Dataset settings" />
      <section className="card pad stack" style={{ maxWidth: 560 }}>
        <Field label="Name"><div className="row"><input className="input" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} /><button className="btn" disabled={!name.trim() || name === detail.name} onClick={() => void save({ name })}>Rename</button></div></Field>
        <div className="stack-sm">
          <strong className="small">Who can use it</strong>
          <label className="check"><input type="radio" name="vis" checked={detail.visibility === "private"} onChange={() => void save({ visibility: "private" })} /> Only me</label>
          <label className="check"><input type="radio" name="vis" checked={detail.visibility === "shared"} onChange={() => void save({ visibility: "shared" })} /> Everyone on this server can ask questions. Only I can change it.</label>
        </div>
      </section>
      <section className="card pad stack" style={{ maxWidth: 560 }}>
        <h3>Delete this dataset</h3>
        <p className="muted small">Removes the data, the definitions and everyone's chats about it. This cannot be undone.</p>
        <div><button className="btn danger" onClick={() => setConfirm(true)}>Delete dataset…</button></div>
      </section>
      <Dialog open={confirm} onClose={() => setConfirm(false)} title={`Delete “${detail.name}”?`}
        footer={<><button className="btn" onClick={() => setConfirm(false)}>Cancel</button><button className="btn danger" onClick={() => void remove()}>Delete for good</button></>}>
        <Callout kind="warn"><span>All chats and definitions for this dataset will be lost too.</span></Callout>
      </Dialog>
    </div>
  );
}
