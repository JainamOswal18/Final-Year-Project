import { useState, type FormEvent } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { Callout, Field, Spinner } from "../ui";

function Card({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="auth">
      <div className="card auth-card">
        <div className="stack-sm"><div className="brand" style={{ padding: 0 }}><span className="brand-mark" aria-hidden="true"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round"><circle cx="10.5" cy="10.5" r="6" /><path d="M15.5 15.5L21 21" /></svg></span>LocalLens</div>
          <h1>{title}</h1>{subtitle && <p className="muted">{subtitle}</p>}</div>
        {children}
      </div>
    </div>
  );
}

function useSubmit(fn: () => Promise<unknown>) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setError("");
    try { await fn(); } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  };
  return { busy, error, submit };
}

export function LoginPage() {
  const { refresh } = useAuth();
  const [u, setU] = useState(""); const [p, setP] = useState("");
  const { busy, error, submit } = useSubmit(async () => { await api.login(u, p); await refresh(); });
  return (
    <Card title="Sign in" subtitle="Ask questions about your data in plain language. Everything stays on this server.">
      <form className="stack" onSubmit={submit}>
        <Field label="Username"><input className="input" autoFocus autoComplete="username" value={u} onChange={(e) => setU(e.target.value)} required /></Field>
        <Field label="Password"><input className="input" type="password" autoComplete="current-password" value={p} onChange={(e) => setP(e.target.value)} required /></Field>
        {error && <Callout kind="bad">{error}</Callout>}
        <button className="btn primary" disabled={busy}>{busy ? <Spinner /> : null} Sign in</button>
      </form>
    </Card>
  );
}

export function SetupPage() {
  const { refresh } = useAuth();
  const [u, setU] = useState(""); const [p, setP] = useState(""); const [p2, setP2] = useState("");
  const { busy, error, submit } = useSubmit(async () => {
    if (p !== p2) throw new Error("The two passwords do not match.");
    await api.setup(u, p); await refresh();
  });
  return (
    <Card title="Welcome to LocalLens" subtitle="Create the administrator account. You can add everyone else afterwards.">
      <form className="stack" onSubmit={submit}>
        <Field label="Username" hint="3-40 letters, digits, dot, dash or underscore"><input className="input" autoFocus autoComplete="username" value={u} onChange={(e) => setU(e.target.value)} required /></Field>
        <Field label="Password" hint="At least 8 characters"><input className="input" type="password" autoComplete="new-password" value={p} onChange={(e) => setP(e.target.value)} required /></Field>
        <Field label="Repeat password"><input className="input" type="password" autoComplete="new-password" value={p2} onChange={(e) => setP2(e.target.value)} required /></Field>
        {error && <Callout kind="bad">{error}</Callout>}
        <button className="btn primary" disabled={busy}>{busy ? <Spinner /> : null} Create administrator</button>
      </form>
    </Card>
  );
}

export function ChangePasswordPage({ forced }: { forced?: boolean }) {
  const { refresh, signOut } = useAuth();
  const [cur, setCur] = useState(""); const [p, setP] = useState(""); const [p2, setP2] = useState("");
  const { busy, error, submit } = useSubmit(async () => {
    if (p !== p2) throw new Error("The two passwords do not match.");
    await api.changePassword(cur, p); await refresh();
  });
  return (
    <Card title="Choose a new password" subtitle={forced ? "Your password was set by an administrator. Pick your own before you continue." : undefined}>
      <form className="stack" onSubmit={submit}>
        <Field label="Current password"><input className="input" type="password" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} required /></Field>
        <Field label="New password" hint="At least 8 characters"><input className="input" type="password" autoComplete="new-password" value={p} onChange={(e) => setP(e.target.value)} required /></Field>
        <Field label="Repeat new password"><input className="input" type="password" autoComplete="new-password" value={p2} onChange={(e) => setP2(e.target.value)} required /></Field>
        {error && <Callout kind="bad">{error}</Callout>}
        <div className="row"><button className="btn primary grow" disabled={busy}>{busy ? <Spinner /> : null} Save password</button>
          {forced && <button type="button" className="btn ghost" onClick={() => void signOut()}>Sign out</button>}</div>
      </form>
    </Card>
  );
}
