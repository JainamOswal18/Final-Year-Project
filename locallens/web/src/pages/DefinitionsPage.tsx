import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { formatNumber } from "../format";
import type { CheckResult, Column, Measure, Rule, Tag } from "../types";
import { Badge, Callout, ChipsInput, Field, Seg, Spinner } from "../ui";
import { columnExample, metricExample, ruleExample } from "../examples";
import { Ex, HowTo, Recipes } from "../help";
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

      <HowTo id="definitions" title="What is this page for? (you can skip it at first)">
        <p>The assistant already understands your columns from the Columns page. Use this page only to teach it things that are <strong>specific to your business</strong>. There are three tools, all optional:</p>
        <ul className="guide-list">
          <li><strong>Metrics</strong>: a number you work out from other numbers. “Profit margin” is profit divided by sales.</li>
          <li><strong>Calculated columns</strong>: a new label or number made for every row. “Order size” is Large when the sale is 1,000 or more.</li>
          <li><strong>Business rules</strong>: a filter applied for you. “Never count cancelled orders.”</li>
        </ul>
        <p>Each section below has its own short guide with examples you can copy. A green ✓ under any formula means it works and shows a sample result; a red ✕ says what to fix. Nothing is saved until you press Save.</p>
      </HowTo>

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
        <HowTo id="def-metrics" title="How to write a metric" defaultOpen={draft.measures.length === 0}>
          <p>A metric is a number people can ask for by name, such as “profit margin by region”. You write the formula once and the assistant uses it every time.</p>
          <Ex label="Worked example: profit margin">
            <Recipes head={["Box", "What to type"]} rows={[
              [<strong key="a">Name</strong>, <><code>profit_margin</code> <span className="muted small">letters, digits and underscores, no spaces</span></>],
              [<strong key="b">Shown as</strong>, <><code>profit margin</code> <span className="muted small">how it is labelled on charts</span></>],
              [<strong key="c">Formula</strong>, <code>SUM(profit) / NULLIF(SUM(sales_amt), 0)</code>],
              [<strong key="d">Other names</strong>, <><code>margin</code>, <code>profitability</code> <span className="muted small">press Enter after each</span></>],
              [<strong key="e">Format</strong>, <>Percent <span className="muted small">so it reads 18.4%, not 0.184</span></>],
              [<strong key="f">Parts add up to the whole</strong>, <>leave unticked <span className="muted small">ratios and averages do not add up</span></>],
            ]} />
            <p>Now “profit margin by region” works.</p>
          </Ex>
          <p><strong>Formula recipes</strong> (use your own column names, exactly as on the Columns page):</p>
          <Recipes head={["You want", "Type"]} rows={[
            ["A total", <code key="1">SUM(sales_amt)</code>],
            ["An average", <code key="2">AVG(sales_amt)</code>],
            ["Biggest or smallest", <><code>MAX(sales_amt)</code> or <code>MIN(sales_amt)</code></>],
            ["One number as a share of another", <code key="3">SUM(profit) / NULLIF(SUM(sales_amt), 0)</code>],
            ["Per unit", <code key="4">SUM(sales_amt) / NULLIF(SUM(quantity), 0)</code>],
          ]} />
          <ul className="guide-list">
            <li><strong>Always divide by <code>NULLIF(x, 0)</code></strong>, as above, so a zero gives a blank instead of an error.</li>
            <li><strong>Tick “Parts add up to the whole”</strong> only for amounts such as sales or quantity. It allows “share of” questions, which would be wrong for a ratio.</li>
            <li>You can use SUM, AVG, COUNT, MIN, MAX, CASE, NULLIF and ROUND.</li>
          </ul>
          <div><button className="btn sm" onClick={() => update((d) => { d.measures.push(metricExample(d.columns, d.measures)); })}>Add an example made from my columns</button></div>
        </HowTo>
        {draft.measures.length === 0 && <div className="card pad muted small">No custom metrics yet. Example: <code>profit_margin = SUM(profit) / NULLIF(SUM(sales_amt), 0)</code></div>}
        {draft.measures.map((m, i) => (
          <div key={i} className={`card item-card ${m.error ? "off" : ""}`}>
            <Off error={m.error} />
            <div className="two-col">
              <Field label="Name" hint="Letters, digits and underscores, no spaces. e.g. profit_margin"><input className={`input mono`} aria-invalid={!NAME.test(m.name) || nameClash(m.name, m.name)} value={m.name} onChange={(e) => update((d) => { d.measures[i].name = e.target.value; })} /></Field>
              <Field label="Shown as" hint="The plain name on charts and in answers"><input className="input" value={m.label} placeholder="e.g. profit margin" onChange={(e) => update((d) => { d.measures[i].label = e.target.value; })} /></Field>
            </div>
            <Field label="Formula" hint="Combine your columns with SUM, AVG, COUNT, MIN, MAX, NULLIF, ROUND. Example: SUM(profit) / NULLIF(SUM(sales_amt), 0)">
              <textarea className="textarea mono" rows={2} value={m.expression} placeholder="SUM(profit) / NULLIF(SUM(sales_amt), 0)" onChange={(e) => update((d) => { d.measures[i].expression = e.target.value; })} />
            </Field>
            <LiveCheck datasetId={detail.id} kind="measure" expression={m.expression} />
            <div className="two-col">
              <Field label="Other names people use" hint="Words your team says for it. Press Enter after each"><ChipsInput label="Synonyms" values={m.synonyms} placeholder="e.g. margin, profitability" onChange={(v) => update((d) => { d.measures[i].synonyms = v; })} /></Field>
              <Field label="Description"><input className="input" maxLength={200} value={m.description} placeholder="What does it mean?" onChange={(e) => update((d) => { d.measures[i].description = e.target.value; })} /></Field>
            </div>
            <div className="row wrap between">
              <div className="row wrap">
                <Seg label="Format" value={m.format} options={[{ value: "number", label: "Number", title: "Shown as 1,234.5" }, { value: "currency", label: "Money", title: "Shown with two decimals, 1,234.50" }, { value: "percent", label: "Percent", title: "0.184 is shown as 18.4%" }]} onChange={(v) => update((d) => { d.measures[i].format = v; })} />
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
        <HowTo id="def-calc" title="How to write a calculated column" defaultOpen={calc.length === 0}>
          <p>A calculated column is a new column that is worked out <strong>for every row</strong> from your other columns. Use it to put rows into bands or to build a label.</p>
          <Ex label="Worked example: order size">
            <Recipes head={["Box", "What to type"]} rows={[
              [<strong key="a">Name</strong>, <code>order_size</code>],
              [<strong key="b">Used as</strong>, <>Category <span className="muted small">the answer is a word, so it groups the numbers</span></>],
              [<strong key="c">Formula for each row</strong>, <code>CASE WHEN sales_amt &gt;= 1000 THEN 'Large' ELSE 'Small' END</code>],
              [<strong key="d">Other names</strong>, <><code>order band</code>, <code>size</code></>],
            ]} />
            <p>Now “sales by order size” works, and so does “only Large orders”.</p>
          </Ex>
          <ul className="guide-list">
            <li><strong>Three bands:</strong> <code>CASE WHEN sales_amt &gt;= 5000 THEN 'Large' WHEN sales_amt &gt;= 1000 THEN 'Medium' ELSE 'Small' END</code>. The first matching line wins.</li>
            <li><strong>Words go in single quotes</strong> ('Large'), numbers do not.</li>
            <li><strong>Used as:</strong> Category when the result is a word, Metric when it is a number you add up, Date when it is a date.</li>
          </ul>
          <div><button className="btn sm" onClick={() => update((d) => { d.columns.push(columnExample(d.columns, d.columns.filter((c) => c.table === "_calc"))); })}>Add an example made from my columns</button></div>
        </HowTo>
        {calc.length === 0 && <div className="card pad muted small">None yet. Example: <code>CASE WHEN sales_amt &gt;= 1000 THEN 'Large' ELSE 'Small' END</code></div>}
        {calc.map(({ c, i }) => (
          <div key={i} className={`card item-card ${c.error ? "off" : ""}`}>
            <Off error={c.error} />
            <div className="two-col">
              <Field label="Name"><input className="input mono" value={c.name} onChange={(e) => update((d) => { d.columns[i].name = e.target.value; })} /></Field>
              <Field label="Used as"><div><Seg<Tag> label="Used as" value={c.tag} options={[{ value: "dimension", label: "Category" }, { value: "metric", label: "Metric" }, { value: "date", label: "Date" }]} cls={(v) => v} onChange={(v) => update((d) => { d.columns[i].tag = v; })} /></div></Field>
            </div>
            <Field label="Formula for each row" hint="Words in single quotes, e.g. CASE WHEN sales_amt >= 1000 THEN 'Large' ELSE 'Small' END"><textarea className="textarea mono" rows={2} value={c.expression} placeholder="CASE WHEN sales_amt >= 1000 THEN 'Large' ELSE 'Small' END" onChange={(e) => update((d) => { d.columns[i].expression = e.target.value; })} /></Field>
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
        <HowTo id="def-rules" title="How to write a business rule" defaultOpen={draft.rules.length === 0}>
          <p>A rule keeps people from having to remember a filter. The condition describes the rows to <strong>keep</strong>.</p>
          <Recipes head={["Rule", "What to type"]} rows={[
            [<><strong>Always on:</strong> leave out cancelled orders</>, <><div>Keep only rows where: <code>status &lt;&gt; 'cancelled'</code></div><div className="muted small">Leave “Applies when the question says” empty. Every answer follows it.</div></>],
            [<><strong>When asked for:</strong> “high value”</>, <><div>Keep only rows where: <code>sales_amt &gt;= 1000</code></div><div className="muted small">Trigger words: <code>high value</code>, <code>big orders</code>. Used only when a question says one of them, such as “high value orders by region”.</div></>],
            [<><strong>Limit to some values</strong></>, <code>category IN ('Furniture', 'Technology')</code>],
          ]} />
          <ul className="guide-list">
            <li><strong>Comparisons:</strong> <code>=</code> <code>&lt;&gt;</code> (not equal) <code>&gt;</code> <code>&gt;=</code> <code>&lt;</code> <code>&lt;=</code>, joined with <code>AND</code> / <code>OR</code>.</li>
            <li><strong>Words go in single quotes</strong> ('cancelled'), numbers do not.</li>
            <li>Untick <strong>Enabled</strong> to pause a rule without deleting it. The answer always lists the rules it used.</li>
          </ul>
          <div><button className="btn sm" onClick={() => update((d) => { d.rules.push(ruleExample(d.columns, d.rules)); })}>Add an example made from my columns</button></div>
        </HowTo>
        {draft.rules.length === 0 && <div className="card pad muted small">None yet. Examples: always leave out cancelled orders (<code>status &lt;&gt; 'cancelled'</code>), or define “high value” (<code>sales_amt &gt;= 1000</code>).</div>}
        {draft.rules.map((r, i) => (
          <div key={i} className={`card item-card ${r.error || !r.enabled ? "off" : ""}`}>
            <Off error={r.error} />
            <div className="row between wrap">
              <Field label="Name"><input className="input mono" style={{ width: 240 }} value={r.name} onChange={(e) => update((d) => { d.rules[i].name = e.target.value; })} /></Field>
              <div className="row"><Badge kind={r.phrases.length ? "accent" : "good"}>{r.phrases.length ? "When asked for" : "Always on"}</Badge>
                <label className="check"><input type="checkbox" checked={r.enabled} onChange={(e) => update((d) => { d.rules[i].enabled = e.target.checked; })} /> Enabled</label></div>
            </div>
            <Field label="Keep only rows where" hint="A condition on your columns. Words in single quotes, e.g. status <> 'cancelled' or sales_amt >= 1000"><textarea className="textarea mono" rows={2} value={r.condition} placeholder="sales_amt >= 1000" onChange={(e) => update((d) => { d.rules[i].condition = e.target.value; })} /></Field>
            <LiveCheck datasetId={detail.id} kind="rule" expression={r.condition} />
            <div className="two-col">
              <Field label="Applies when the question says" hint="Leave empty to apply to every question. Or add words such as: high value, big orders"><ChipsInput label="Trigger words" values={r.phrases} placeholder="e.g. high value" onChange={(v) => update((d) => { d.rules[i].phrases = v; })} /></Field>
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
