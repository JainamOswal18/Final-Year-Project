import { useState, type FormEvent } from "react";
import { api } from "../api";
import { loadTheme, saveTheme, type ThemePref } from "../auth";
import { prettify } from "../format";
import { Callout, Field, Seg, Spinner, useAsync, useToast } from "../ui";
import { PageHead } from "./DatasetLoader";

function ChartPrefs() {
  const toast = useToast();
  const { data, loading, error } = useAsync(() => api.prefs(), []);
  const [sort, setSort] = useState<"asc" | "desc" | null>(null);
  const [over, setOver] = useState<Record<string, string> | null>(null);
  const [saving, setSaving] = useState(false);
  if (loading) return <Spinner />;
  if (error || !data) return <Callout kind="bad">{error}</Callout>;
  const curSort = sort ?? data.sort;
  const cur = over ?? data.chart_overrides;
  const save = async () => {
    setSaving(true);
    try { await api.savePrefs({ sort: curSort, chart_overrides: cur }); toast("Preferences saved."); } catch (e) { toast((e as Error).message, true); } finally { setSaving(false); }
  };
  return (
    <section className="card pad stack" style={{ maxWidth: 620 }}>
      <div><h2>Charts</h2><p className="muted small">Applied to your answers. The assistant still picks the chart type that fits the result unless you choose one here.</p></div>
      <div className="stack-sm"><strong className="small">Order of bars</strong>
        <Seg label="Sort" value={curSort} options={[{ value: "desc", label: "Largest first" }, { value: "asc", label: "Smallest first" }]} onChange={setSort} /></div>
      {Object.entries(data.choices).map(([intent, choices]) => (
        <label className="field" key={intent} style={{ maxWidth: 320 }}>{prettify(intent)} questions
          <select className="select" value={cur[intent] ?? ""} onChange={(e) => { const n = { ...cur }; if (e.target.value) n[intent] = e.target.value; else delete n[intent]; setOver(n); }}>
            <option value="">Automatic</option>{choices.map((c) => <option key={c} value={c}>{prettify(c === "hbar" ? "horizontal bars" : c === "bar" ? "vertical bars" : c)}</option>)}
          </select></label>
      ))}
      <div><button className="btn primary" onClick={() => void save()} disabled={saving}>{saving ? <Spinner /> : null} Save</button></div>
    </section>
  );
}

function PasswordForm() {
  const toast = useToast();
  const [cur, setCur] = useState(""); const [p, setP] = useState(""); const [p2, setP2] = useState("");
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setError("");
    if (p !== p2) { setError("The two passwords do not match."); return; }
    setBusy(true);
    try { await api.changePassword(cur, p); toast("Password changed. Other devices were signed out."); setCur(""); setP(""); setP2(""); }
    catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  };
  return (
    <section className="card pad" style={{ maxWidth: 620 }}>
      <form className="stack" onSubmit={submit}>
        <h2>Password</h2>
        <Field label="Current password"><input className="input" type="password" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} required /></Field>
        <div className="two-col">
          <Field label="New password" hint="At least 8 characters"><input className="input" type="password" autoComplete="new-password" value={p} onChange={(e) => setP(e.target.value)} required /></Field>
          <Field label="Repeat new password"><input className="input" type="password" autoComplete="new-password" value={p2} onChange={(e) => setP2(e.target.value)} required /></Field>
        </div>
        {error && <Callout kind="bad">{error}</Callout>}
        <div><button className="btn" disabled={busy}>{busy ? <Spinner /> : null} Change password</button></div>
      </form>
    </section>
  );
}

export default function SettingsPage() {
  const [theme, setTheme] = useState<ThemePref>(loadTheme());
  return (
    <div className="page">
      <PageHead title="Preferences" />
      <section className="card pad stack-sm" style={{ maxWidth: 620 }}>
        <h2>Appearance</h2>
        <Seg label="Theme" value={theme} options={[{ value: "system", label: "Match device" }, { value: "light", label: "Light" }, { value: "dark", label: "Dark" }]} onChange={(t) => { setTheme(t); saveTheme(t); }} />
      </section>
      <ChartPrefs />
      <PasswordForm />
    </div>
  );
}
