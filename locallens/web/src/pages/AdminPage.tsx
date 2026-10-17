import { useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { timeAgo } from "../format";
import type { User } from "../types";
import { Badge, Callout, Dialog, Field, Spinner, useAsync, useToast } from "../ui";
import { PageHead } from "./DatasetLoader";

function NewUserDialog({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const [name, setName] = useState(""); const [role, setRole] = useState("user");
  const [made, setMade] = useState<{ username: string; pw: string } | null>(null);
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const close = () => { setMade(null); setName(""); setError(""); onClose(); };
  const create = async () => {
    setBusy(true); setError("");
    try { const u = await api.createUser(name.trim(), role); setMade({ username: u.username, pw: u.temporary_password }); onDone(); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onClose={close} title={made ? "User created" : "Add a user"}
      footer={made ? <button className="btn primary" onClick={close}>Done</button> : <><button className="btn" onClick={close}>Cancel</button><button className="btn primary" disabled={busy || name.trim().length < 3} onClick={() => void create()}>{busy ? <Spinner /> : null} Create</button></>}>
      {made ? (
        <div className="stack"><Callout kind="good"><span>Give <strong>{made.username}</strong> this temporary password. They must choose their own at first sign-in. It is not shown again.</span></Callout>
          <pre className="code" style={{ fontSize: 16, userSelect: "all" }}>{made.pw}</pre></div>
      ) : (
        <>
          <Field label="Username" hint="3-40 letters, digits, dot, dash or underscore"><input className="input" autoFocus value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label="Role"><select className="select" value={role} onChange={(e) => setRole(e.target.value)}><option value="user">User</option><option value="admin">Administrator</option></select></Field>
          {error && <Callout kind="bad">{error}</Callout>}
        </>
      )}
    </Dialog>
  );
}

function Users() {
  const { user: me } = useAuth();
  const toast = useToast();
  const { data, loading, error, reload } = useAsync(() => api.users(), []);
  const [open, setOpen] = useState(false);
  const [reset, setReset] = useState<{ username: string; pw: string } | null>(null);
  const [del, setDel] = useState<User | null>(null);
  const act = async (fn: () => Promise<unknown>) => { try { await fn(); reload(); } catch (e) { toast((e as Error).message, true); } };
  return (
    <section className="stack">
      <div className="row between"><h2>People</h2><button className="btn primary" onClick={() => setOpen(true)}>Add a user</button></div>
      {loading ? <Spinner /> : error ? <Callout kind="bad">{error}</Callout> : (
        <div className="card" style={{ overflow: "auto" }}>
          <table className="t edit">
            <thead><tr><th>User</th><th>Role</th><th>Last sign-in</th><th /></tr></thead>
            <tbody>
              {data?.map((u) => (
                <tr key={u.id}>
                  <td><strong>{u.username}</strong> {u.id === me?.id && <Badge>you</Badge>} {!u.active && <Badge kind="bad">disabled</Badge>} {u.must_change_password && <Badge kind="warn">temporary password</Badge>}</td>
                  <td><select className="select sm" style={{ width: 130 }} aria-label={`Role of ${u.username}`} value={u.role} onChange={(e) => void act(() => api.patchUser(u.id, { role: e.target.value }))}><option value="user">User</option><option value="admin">Administrator</option></select></td>
                  <td className="muted small">{u.last_login ? timeAgo(u.last_login) : "never"}</td>
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    <button className="btn ghost sm" onClick={() => void act(async () => { const r = await api.patchUser(u.id, { new_password: "" }); setReset({ username: u.username, pw: r.temporary_password ?? "" }); })}>Reset password</button>
                    <button className="btn ghost sm" onClick={() => void act(() => api.patchUser(u.id, { active: !u.active }))}>{u.active ? "Disable" : "Enable"}</button>
                    <button className="btn ghost sm" style={{ color: "var(--bad)" }} disabled={u.id === me?.id} onClick={() => setDel(u)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <NewUserDialog open={open} onClose={() => setOpen(false)} onDone={reload} />
      <Dialog open={!!reset} onClose={() => setReset(null)} title="Password reset" footer={<button className="btn primary" onClick={() => setReset(null)}>Done</button>}>
        <Callout kind="good"><span>New temporary password for <strong>{reset?.username}</strong>. They must change it at next sign-in.</span></Callout>
        <pre className="code" style={{ fontSize: 16, userSelect: "all" }}>{reset?.pw}</pre>
      </Dialog>
      <Dialog open={!!del} onClose={() => setDel(null)} title={`Delete ${del?.username}?`}
        footer={<><button className="btn" onClick={() => setDel(null)}>Cancel</button><button className="btn danger" onClick={() => void act(async () => { await api.deleteUser(del!.id); setDel(null); })}>Delete user</button></>}>
        <Callout kind="warn"><span>Their datasets and chats are deleted with them.</span></Callout>
      </Dialog>
    </section>
  );
}

function Feedback() {
  const [neg, setNeg] = useState(true);
  const { data, loading, error } = useAsync(() => api.feedback(neg), [neg]);
  return (
    <section className="stack">
      <div className="row between wrap"><div><h2>Answers people flagged</h2><p className="muted small">Wrong answers make the best test questions: copy them into the evaluation set, then fix the cause.</p></div>
        <label className="check"><input type="checkbox" checked={neg} onChange={(e) => setNeg(e.target.checked)} /> Only thumbs-down</label></div>
      {loading ? <Spinner /> : error ? <Callout kind="bad">{error}</Callout> : data?.length === 0 ? <div className="card pad muted small">Nothing flagged yet.</div> : (
        <div className="stack-sm">{data?.map((f) => (
          <details key={f.id} className="card pad fold">
            <summary><strong>{f.question}</strong> <span className="muted small">· {f.user} · {timeAgo(f.created_at)} {f.rating < 0 ? "· 👎" : "· 👍"}</span></summary>
            <div className="stack-sm">
              {f.note && <div className="small">Note: {f.note}</div>}
              {f.error && <Callout kind="warn"><span>{f.error}</span></Callout>}
              {f.frame && <pre className="code">{JSON.stringify(f.frame, null, 2)}</pre>}
              {f.sql && <pre className="code">{f.sql}</pre>}
            </div>
          </details>))}</div>
      )}
    </section>
  );
}

function System() {
  const { data } = useAsync(() => api.health(), []);
  return (
    <section className="card pad stack-sm"><h2>System</h2>
      <div className="row wrap">
        <Badge kind={data?.model_present ? "good" : "bad"}>Model file {data?.model_present ? "present" : "missing"}</Badge>
        <Badge kind={data?.model_loaded ? "good" : "warn"}>{data?.model_loaded ? "Model loaded" : "Model not loaded yet"}</Badge>
      </div>
      {data?.model_error && <Callout kind="bad"><span>{data.model_error}</span></Callout>}
    </section>
  );
}

export default function AdminPage() {
  return <div className="page"><PageHead title="Administration" subtitle="People, and the answers they flagged." /><System /><Users /><Feedback /></div>;
}
