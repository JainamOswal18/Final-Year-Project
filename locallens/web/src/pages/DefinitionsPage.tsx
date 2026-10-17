import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { formatNumber } from "../format";
import type { CheckResult, Column, Measure, Rule, Tag } from "../types";
import { Badge, Callout, ChipsInput, Field, Seg, Spinner } from "../ui";
import { SaveBar, useRegistryEditor } from "../useRegistryEditor";
import { PageHead } from "./DatasetLoader";

const NAME = /^[A-Za-z_][A-Za-z0-9_]*$/;
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

/** Checks an expression on the server a moment after typing stops and shows what it produces. */
function LiveCheck({ datasetId, kind, expression }: { datasetId: string; kind: "measure" | "column" | "rule"; expression: string }) {
  const [res, setRes] = useState<CheckResult | null>(null);
  const [busy, setBusy] = useState(false);
  const seq = useRef(0);
  useEffect(() => {
    if (!expression.trim()) { setRes(null); return; }
    const mine = ++seq.current;
    const t = setTimeout(() => {
      setBusy(true);
      api.check(datasetId, kind, expression).then((r) => mine === seq.current && setRes(r), (e: Error) => mine === seq.current && setRes({ ok: false, error: e.message }))
        .finally(() => mine === seq.current && setBusy(false));
    }, 600);
    return () => clearTimeout(t);
  }, [datasetId, kind, expression]);
  if (!expression.trim()) return null;
  if (busy && !res) return <div className="small muted row"><Spinner /> Checking…</div>;
  if (!res) return null;
  if (!res.ok) return <div className="small" style={{ color: "var(--bad)" }} role="alert">✕ {res.error}</div>;
  const p = res.preview ?? {};
  return (
    <div className="small" style={{ color: "var(--good)" }}>
      ✓ Valid
      {p.value !== undefined && p.value !== null && <span className="muted"> · gives {formatNumber(p.value)} on a sample</span>}
      {p.values && <span className="muted"> · e.g. {p.values.filter(Boolean).slice(0, 5).join(", ")}</span>}
      {p.matching !== undefined && <span className="muted"> · matches {p.matching} of {p.of} sample rows</span>}
    </div>
  );
}

function Off({ error }: { error: string }) {
  return error ? <Callout kind="warn"><span><strong>Switched off.</strong> {error}</span></Callout> : null;
}

export default function DefinitionsPage() {
  const { draft, update, dirty, saving, save, discard, detail } = useRegistryEditor();
  const calc = draft.columns.map((c, i) => ({ c, i })).filter(({ c }) => c.table === "_calc");
  const usable = draft.columns.filter((c) => c.flat_name && c.tag !== "ignore" && !c.error);
  const nameClash = (n: string, self: string) => draft.measures.some((m) => m.name === n && m !== draft.measures.find((x) => x.name === self)) ||
    draft.columns.some((c) => c.name === n || c.flat_name === n);

  return (
    <div className="page">
      <PageHead title="Definitions" subtitle="Teach the assistant your business: how metrics are calculated, which rows to leave out, and what your terms mean. It uses these every time it answers." />
      {detail.problems.length > 0 && (
        <Callout kind="warn"><div className="stack-sm"><strong>Some definitions are switched off</strong>{detail.problems.map((p, i) => <div key={i} className="small">{p}</div>)}</div></Callout>
      )}

      <section className="card pad stack" aria-labelledby="ctx">
        <div><h2 id="ctx">About this data</h2><p className="muted small">A sentence or two in your own words. It is shown to the assistant with every question.</p></div>
        <Field label="Description" hint={`${draft.description.length}/600`}>
          <textarea className="textarea" maxLength={600} value={draft.description} placeholder="e.g. Retail sales for our stores, one row per order, amounts in rupees." onChange={(e) => update((d) => { d.description = e.target.value; })} />
        </Field>
        <label className="field" style={{ maxWidth: 320 }}>Financial year starts in
          <select className="select" value={draft.fiscal_start_month} onChange={(e) => update((d) => { d.fiscal_start_month = Number(e.target.value); })}>
            {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
          </select>
          <span className="hint">“Last quarter”, “this year” and “FY2025” follow it. A financial year is named after the year it ends in.</span></label>
      </section>

      <section className="stack" aria-labelledby="meas">
        <div className="row between wrap"><div><h2 id="meas">Metrics</h2><p className="muted small">Your own calculations, such as profit margin or average order value.</p></div>
          <button className="btn" onClick={() => update((d) => { d.measures.push({ name: `metric_${d.measures.length + 1}`, expression: "", label: "", description: "", synonyms: [], format: "number", additive: false, error: "" } as Measure); })}>Add a metric</button></div>
        {draft.measures.length === 0 && <div className="card pad muted small">No custom metrics yet. Example: <code>profit_margin = SUM(profit) / SUM(sales_amt)</code></div>}
        {draft.measures.map((m, i) => (
          <div key={i} className={`card item-card ${m.error ? "off" : ""}`}>
            <Off error={m.error} />
            <div className="two-col">
              <Field label="Name" hint="Letters, digits and underscore. Used internally."><input className={`input mono`} aria-invalid={!NAME.test(m.name) || nameClash(m.name, m.name)} value={m.name} onChange={(e) => update((d) => { d.measures[i].name = e.target.value; })} /></Field>
              <Field label="Shown as"><input className="input" value={m.label} placeholder="e.g. profit margin" onChange={(e) => update((d) => { d.measures[i].label = e.target.value; })} /></Field>
            </div>
            <Field label="Formula" hint="Use SUM, AVG, COUNT, MIN, MAX, CASE, NULLIF, ROUND and your column names.">
              <textarea className="textarea mono" rows={2} value={m.expression} placeholder="SUM(profit) / NULLIF(SUM(sales_amt), 0)" onChange={(e) => update((d) => { d.measures[i].expression = e.target.value; })} />
            </Field>
            <LiveCheck datasetId={detail.id} kind="measure" expression={m.expression} />
            <div className="two-col">
              <Field label="Other names people use"><ChipsInput label="Synonyms" values={m.synonyms} placeholder="e.g. margin percent" onChange={(v) => update((d) => { d.measures[i].synonyms = v; })} /></Field>
              <Field label="Description"><input className="input" maxLength={200} value={m.description} placeholder="What does it mean?" onChange={(e) => update((d) => { d.measures[i].description = e.target.value; })} /></Field>
            </div>
            <div className="row wrap between">
              <div className="row wrap">
                <Seg label="Format" value={m.format} options={[{ value: "number", label: "Number" }, { value: "currency", label: "Money" }, { value: "percent", label: "Percent" }]} onChange={(v) => update((d) => { d.measures[i].format = v; })} />
                <label className="check"><input type="checkbox" checked={m.additive} onChange={(e) => update((d) => { d.measures[i].additive = e.target.checked; })} /> Parts add up to the whole <span className="faint small">(allows “share of”)</span></label>
              </div>
              <button className="btn danger sm" onClick={() => update((d) => { d.measures.splice(i, 1); })}>Delete</button>
            </div>
          </div>
        ))}
      </section>

      <section className="stack" aria-labelledby="calc">
        <div className="row between wrap"><div><h2 id="calc">Calculated columns</h2><p className="muted small">A new column worked out for every row, such as an order size band. It can then be grouped, filtered or summed like any other.</p></div>
          <button className="btn" onClick={() => update((d) => { d.columns.push({ table: "_calc", name: `column_${calc.length + 1}`, flat_name: "", tag: "dimension", description: "", expression: "", error: "", synonyms: [], samples: [], values: [] } as Column); })}>Add a column</button></div>
        {calc.length === 0 && <div className="card pad muted small">None yet. Example: <code>CASE WHEN sales_amt &gt;= 1000 THEN 'Large' ELSE 'Small' END</code></div>}
        {calc.map(({ c, i }) => (
          <div key={i} className={`card item-card ${c.error ? "off" : ""}`}>
            <Off error={c.error} />
            <div className="two-col">
              <Field label="Name"><input className="input mono" value={c.name} onChange={(e) => update((d) => { d.columns[i].name = e.target.value; })} /></Field>
              <Field label="Used as"><div><Seg<Tag> label="Used as" value={c.tag} options={[{ value: "dimension", label: "Category" }, { value: "metric", label: "Metric" }, { value: "date", label: "Date" }]} cls={(v) => v} onChange={(v) => update((d) => { d.columns[i].tag = v; })} /></div></Field>
            </div>
            <Field label="Formula for each row"><textarea className="textarea mono" rows={2} value={c.expression} placeholder="CASE WHEN sales_amt >= 1000 THEN 'Large' ELSE 'Small' END" onChange={(e) => update((d) => { d.columns[i].expression = e.target.value; })} /></Field>
            <LiveCheck datasetId={detail.id} kind="column" expression={c.expression} />
            <div className="two-col">
              <Field label="Other names people use"><ChipsInput label="Synonyms" values={c.synonyms} placeholder="e.g. order size" onChange={(v) => update((d) => { d.columns[i].synonyms = v; })} /></Field>
              <Field label="Description"><input className="input" maxLength={200} value={c.description} onChange={(e) => update((d) => { d.columns[i].description = e.target.value; })} /></Field>
            </div>
            <div className="row between"><span className="tiny faint">Can use: {usable.slice(0, 8).map((x) => x.flat_name).join(", ")}{usable.length > 8 ? "…" : ""}</span>
              <button className="btn danger sm" onClick={() => update((d) => { d.columns.splice(i, 1); })}>Delete</button></div>
          </div>
        ))}
      </section>

      <section className="stack" aria-labelledby="rules">
        <div className="row between wrap"><div><h2 id="rules">Business rules</h2><p className="muted small">Filters applied for you. A rule with no trigger words always applies; with trigger words it applies when a question uses one of them.</p></div>
          <button className="btn" onClick={() => update((d) => { d.rules.push({ name: `rule_${d.rules.length + 1}`, condition: "", phrases: [], description: "", enabled: true, error: "" } as Rule); })}>Add a rule</button></div>
        {draft.rules.length === 0 && <div className="card pad muted small">None yet. Examples: always leave out cancelled orders (<code>status &lt;&gt; 'cancelled'</code>), or define “high value” (<code>sales_amt &gt;= 1000</code>).</div>}
        {draft.rules.map((r, i) => (
          <div key={i} className={`card item-card ${r.error || !r.enabled ? "off" : ""}`}>
            <Off error={r.error} />
            <div className="row between wrap">
              <Field label="Name"><input className="input mono" style={{ width: 240 }} value={r.name} onChange={(e) => update((d) => { d.rules[i].name = e.target.value; })} /></Field>
              <div className="row"><Badge kind={r.phrases.length ? "accent" : "good"}>{r.phrases.length ? "When asked for" : "Always on"}</Badge>
                <label className="check"><input type="checkbox" checked={r.enabled} onChange={(e) => update((d) => { d.rules[i].enabled = e.target.checked; })} /> Enabled</label></div>
            </div>
            <Field label="Keep only rows where" hint="A condition on your columns."><textarea className="textarea mono" rows={2} value={r.condition} placeholder="sales_amt >= 1000" onChange={(e) => update((d) => { d.rules[i].condition = e.target.value; })} /></Field>
            <LiveCheck datasetId={detail.id} kind="rule" expression={r.condition} />
            <div className="two-col">
              <Field label="Applies when the question says" hint="Leave empty to apply to every question."><ChipsInput label="Trigger words" values={r.phrases} placeholder="e.g. high value" onChange={(v) => update((d) => { d.rules[i].phrases = v; })} /></Field>
              <Field label="Description"><input className="input" maxLength={200} value={r.description} onChange={(e) => update((d) => { d.rules[i].description = e.target.value; })} /></Field>
            </div>
            <div className="row" style={{ justifyContent: "flex-end" }}><button className="btn danger sm" onClick={() => update((d) => { d.rules.splice(i, 1); })}>Delete</button></div>
          </div>
        ))}
      </section>
      <SaveBar dirty={dirty} saving={saving} onSave={() => void save()} onDiscard={discard} />
    </div>
  );
}
